package cli

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"strings"
	"time"
	_ "time/tzdata"

	"logparser/internal/ingest"
	"logparser/internal/model"
)

type inputs []string

func (v *inputs) String() string     { return strings.Join(*v, ",") }
func (v *inputs) Set(s string) error { *v = append(*v, s); return nil }

func Run(args []string, stderr io.Writer) error {
	if len(args) == 1 && args[0] == "version" {
		fmt.Fprintln(stderr, model.ParserVersion)
		return nil
	}
	if len(args) == 0 || args[0] == "--help" || args[0] == "-h" {
		fmt.Fprintln(stderr, "Usage: logparser parse --input FILE [--input FILE...] --dataset-id ID --output events.jsonl [--report FILE] [--timezone UTC]")
		return nil
	}
	if args[0] != "parse" {
		return fmt.Errorf("unknown command %q", args[0])
	}
	f := flag.NewFlagSet("parse", flag.ContinueOnError)
	f.SetOutput(stderr)
	var paths inputs
	f.Var(&paths, "input", "local UTF-8 .log file (repeatable)")
	dataset := f.String("dataset-id", "", "dataset identifier")
	output := f.String("output", "", "JSONL output path")
	reportPath := f.String("report", "", "report path; default OUTPUT.report.json")
	zone := f.String("timezone", "UTC", "assumed IANA timezone of source timestamps")
	if err := f.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return nil
		}
		return err
	}
	if len(paths) == 0 || strings.TrimSpace(*dataset) == "" || *output == "" || f.NArg() != 0 {
		return fmt.Errorf("parse requires --input, --dataset-id and --output, with no positional arguments")
	}
	loc, err := time.LoadLocation(*zone)
	if err != nil {
		return fmt.Errorf("invalid timezone: %w", err)
	}
	if *reportPath == "" {
		*reportPath = *output + ".report.json"
	}
	r, err := ingest.Run(ingest.Config{Inputs: paths, Output: *output, Report: *reportPath, DatasetID: *dataset, Location: loc})
	if err == nil {
		fmt.Fprintf(stderr, "Parsed %d lines from %d files in %.3fs; report: %s\n", r.PhysicalLines, len(r.Files), r.ElapsedSeconds, *reportPath)
	}
	return err
}
