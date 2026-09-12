package cli

import (
	"bytes"
	"testing"
)

func TestUsageAndInvalidConfiguration(t *testing.T) {
	for _, args := range [][]string{nil, {"--help"}, {"parse", "--help"}, {"version"}} {
		var out bytes.Buffer
		if err := Run(args, &out); err != nil || out.Len() == 0 {
			t.Fatalf("help %v: %v", args, err)
		}
	}
	for _, args := range [][]string{{"unknown"}, {"parse"}, {"parse", "--input", "x", "--dataset-id", "test", "--output", "out", "--timezone", "not/a/timezone"}} {
		var out bytes.Buffer
		if err := Run(args, &out); err == nil {
			t.Fatalf("invalid configuration accepted: %v", args)
		}
	}
}
