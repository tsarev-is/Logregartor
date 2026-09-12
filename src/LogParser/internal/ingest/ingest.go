package ingest

import (
	"bufio"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf8"

	"logparser/internal/model"
	"logparser/internal/openstack"
)

type Config struct {
	Inputs                    []string
	Output, Report, DatasetID string
	Location                  *time.Location
}

type FileReport struct {
	SourceFile            string            `json:"source_file"`
	SourceSHA256          string            `json:"source_sha256"`
	PhysicalLines         uint64            `json:"physical_lines"`
	ParseCounts           map[string]uint64 `json:"parse_counts"`
	HeadersWithoutContext uint64            `json:"headers_without_request_context"`
	EmptyMessages         uint64            `json:"empty_messages"`
	Features              map[string]uint64 `json:"features"`
}

type Report struct {
	SchemaVersion  int          `json:"schema_version"`
	ParserVersion  string       `json:"parser_version"`
	DatasetID      string       `json:"dataset_id"`
	Timezone       string       `json:"timezone_assumption"`
	EventsSHA256   string       `json:"events_sha256"`
	PhysicalLines  uint64       `json:"physical_lines"`
	Files          []FileReport `json:"files"`
	ElapsedSeconds float64      `json:"elapsed_seconds"`
}

func Run(cfg Config) (Report, error) {
	started := time.Now()
	report := Report{SchemaVersion: model.SchemaVersion, ParserVersion: model.ParserVersion,
		DatasetID: cfg.DatasetID, Timezone: cfg.Location.String(), Files: []FileReport{}}
	if err := distinctPaths(append(append([]string{}, cfg.Inputs...), cfg.Output, cfg.Report)); err != nil {
		return report, err
	}
	out, err := os.CreateTemp(filepath.Dir(cfg.Output), ".logparser-events-*")
	if err != nil {
		return report, err
	}
	defer os.Remove(out.Name())
	defer out.Close()
	hash := sha256.New()
	writer := bufio.NewWriter(io.MultiWriter(out, hash))
	encoder := json.NewEncoder(writer)
	encoder.SetEscapeHTML(false)
	seen := map[string]bool{}
	for _, path := range cfg.Inputs {
		f, err := parseFile(path, cfg, encoder)
		if err != nil {
			return report, fmt.Errorf("%s: %w", path, err)
		}
		if seen[f.SourceSHA256] {
			return report, fmt.Errorf("duplicate source contents: %s", path)
		}
		seen[f.SourceSHA256] = true
		report.Files = append(report.Files, f)
		report.PhysicalLines += f.PhysicalLines
	}
	if err := writer.Flush(); err != nil {
		return report, err
	}
	if err := out.Sync(); err != nil {
		return report, err
	}
	if err := out.Close(); err != nil {
		return report, err
	}
	report.EventsSHA256 = fmt.Sprintf("%x", hash.Sum(nil))
	report.ElapsedSeconds = time.Since(started).Seconds()
	rf, err := os.CreateTemp(filepath.Dir(cfg.Report), ".logparser-report-*")
	if err != nil {
		return report, err
	}
	defer os.Remove(rf.Name())
	defer rf.Close()
	if err = json.NewEncoder(rf).Encode(report); err != nil {
		return report, err
	}
	if err = rf.Sync(); err != nil {
		return report, err
	}
	if err = rf.Close(); err != nil {
		return report, err
	}
	// Consumers require the report hash, so a crash between renames cannot publish
	// an incomplete or mismatched pair of artifacts.
	if err = os.Rename(out.Name(), cfg.Output); err != nil {
		return report, err
	}
	if err = os.Rename(rf.Name(), cfg.Report); err != nil {
		return report, err
	}
	return report, nil
}

func parseFile(path string, cfg Config, encoder *json.Encoder) (FileReport, error) {
	r := FileReport{SourceFile: filepath.Base(path), ParseCounts: map[string]uint64{}, Features: map[string]uint64{}}
	f, err := os.Open(path)
	if err != nil {
		return r, err
	}
	defer f.Close()
	stat, err := f.Stat()
	if err != nil {
		return r, err
	}
	if !stat.Mode().IsRegular() {
		return r, fmt.Errorf("input must be a regular file")
	}
	hash := sha256.New()
	if _, err = io.Copy(hash, f); err != nil {
		return r, err
	}
	r.SourceSHA256 = fmt.Sprintf("%x", hash.Sum(nil))
	if _, err = f.Seek(0, io.SeekStart); err != nil {
		return r, err
	}
	hash.Reset()
	reader := bufio.NewReader(io.TeeReader(f, hash))
	p := openstack.Parser{Location: cfg.Location}
	for {
		line, err := reader.ReadString('\n')
		if err != nil && err != io.EOF {
			return r, err
		}
		if len(line) > 0 {
			r.PhysicalLines++
			if !utf8.ValidString(line) {
				return r, fmt.Errorf("line %d: input is not UTF-8", r.PhysicalLines)
			}
			ending := ""
			if strings.HasSuffix(line, "\r\n") {
				ending = "\r\n"
			} else if strings.HasSuffix(line, "\n") {
				ending = "\n"
			}
			raw := strings.TrimSuffix(line, ending)
			e := p.Parse(raw, ending, r.SourceFile, r.SourceSHA256, cfg.DatasetID, r.PhysicalLines)
			if err := encoder.Encode(e); err != nil {
				return r, err
			}
			r.ParseCounts[e.ParseStatus]++
			if e.SourceName != nil && e.ContextRaw == nil {
				r.HeadersWithoutContext++
			}
			if e.SourceName != nil && e.Message == "" {
				r.EmptyMessages++
			}
			for k, found := range map[string]bool{
				"instance_id": e.InstanceID != nil, "request_id": e.RequestID != nil,
				"http_status": e.HTTPStatus != nil, "build_duration_seconds": e.BuildDuration != nil,
				"spawn_duration_seconds": e.SpawnDuration != nil, "destroy_duration_seconds": e.DestroyDuration != nil,
				"resources": len(e.Parameters) > 0,
			} {
				if found {
					r.Features[k]++
				}
			}
		}
		if err == io.EOF {
			break
		}
	}
	if fmt.Sprintf("%x", hash.Sum(nil)) != r.SourceSHA256 {
		return r, fmt.Errorf("source changed during parsing")
	}
	return r, nil
}

func distinctPaths(paths []string) error {
	for i, path := range paths {
		a, err := filepath.Abs(path)
		if err != nil {
			return err
		}
		as, _ := os.Stat(path)
		for _, other := range paths[:i] {
			b, err := filepath.Abs(other)
			if err != nil {
				return err
			}
			bs, _ := os.Stat(other)
			if a == b || (as != nil && bs != nil && os.SameFile(as, bs)) {
				return fmt.Errorf("input/output paths must be distinct: %s", path)
			}
		}
	}
	return nil
}
