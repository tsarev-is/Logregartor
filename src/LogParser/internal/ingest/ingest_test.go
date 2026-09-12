package ingest

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"logparser/internal/model"
)

func TestPhysicalLinesAndExactSource(t *testing.T) {
	dir := t.TempDir()
	input := filepath.Join(dir, "input.log")
	raw := "nova.log 2017-05-14 21:43:33.901 1 ERROR nova.compute.manager Traceback (most recent call last):\r\n\n" + strings.Repeat("x", 100000)
	if err := os.WriteFile(input, []byte(raw), 0600); err != nil {
		t.Fatal(err)
	}
	cfg := Config{Inputs: []string{input}, Output: filepath.Join(dir, "out.jsonl"), Report: filepath.Join(dir, "report.json"), DatasetID: "test", Location: time.UTC}
	r, err := Run(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if r.PhysicalLines != 3 || r.Files[0].HeadersWithoutContext != 1 || r.Files[0].ParseCounts["empty"] != 1 || r.Files[0].ParseCounts["unparsed"] != 1 {
		t.Fatalf("counts: %+v", r)
	}
	output, err := os.ReadFile(cfg.Output)
	if err != nil {
		t.Fatal(err)
	}
	if r.EventsSHA256 != fmt.Sprintf("%x", sha256.Sum256(output)) {
		t.Fatal("output checksum mismatch")
	}
	var reconstructed strings.Builder
	for i, line := range strings.Split(strings.TrimSuffix(string(output), "\n"), "\n") {
		var e model.Event
		if err := json.Unmarshal([]byte(line), &e); err != nil {
			t.Fatal(err)
		}
		if e.LineStart != uint64(i+1) || e.LineEnd != e.LineStart {
			t.Fatal("nonphysical numbering")
		}
		reconstructed.WriteString(e.RawText + e.LineEnding)
	}
	if reconstructed.String() != raw {
		t.Fatal("source bytes changed")
	}
}

func TestEmptyFileAndFailedInputDoNotPublish(t *testing.T) {
	dir := t.TempDir()
	input := filepath.Join(dir, "input.log")
	os.WriteFile(input, nil, 0600)
	cfg := Config{Inputs: []string{input}, Output: filepath.Join(dir, "out"), Report: filepath.Join(dir, "report"), DatasetID: "test", Location: time.UTC}
	r, err := Run(cfg)
	if err != nil || r.PhysicalLines != 0 || len(r.Files) != 1 {
		t.Fatalf("empty file: %+v %v", r, err)
	}
	before, _ := os.ReadFile(cfg.Report)
	os.WriteFile(input, []byte{0xff, '\n'}, 0600)
	if _, err = Run(cfg); err == nil {
		t.Fatal("invalid UTF-8 accepted")
	}
	after, _ := os.ReadFile(cfg.Report)
	if string(before) != string(after) {
		t.Fatal("failed parse replaced previous report")
	}
	data, _ := os.ReadFile(cfg.Output)
	if len(data) != 0 {
		t.Fatal("failed parse published data")
	}
}

func TestInputOutputAliasingAndDuplicateSources(t *testing.T) {
	dir := t.TempDir()
	a, b := filepath.Join(dir, "a.log"), filepath.Join(dir, "b.log")
	os.WriteFile(a, []byte("hello\n"), 0600)
	os.WriteFile(b, []byte("hello\n"), 0600)
	cfg := Config{Inputs: []string{a, b}, Output: filepath.Join(dir, "out"), Report: filepath.Join(dir, "report"), DatasetID: "test", Location: time.UTC}
	if _, err := Run(cfg); err == nil {
		t.Fatal("duplicate source accepted")
	}
	if _, err := os.Stat(cfg.Output); !os.IsNotExist(err) {
		t.Fatal("failed import published output")
	}
	cfg.Inputs = []string{a}
	cfg.Output = a
	if _, err := Run(cfg); err == nil {
		t.Fatal("output can overwrite source")
	}
	alias := filepath.Join(dir, "alias")
	if err := os.Link(a, alias); err != nil {
		t.Fatal(err)
	}
	cfg.Output = alias
	if _, err := Run(cfg); err == nil {
		t.Fatal("hardlinked output can overwrite source")
	}
}
