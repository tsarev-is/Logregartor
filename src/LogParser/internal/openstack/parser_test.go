package openstack

import (
	"strings"
	"testing"
	"time"
)

const testHeader = "nova-compute.log.1 2017-05-14 21:43:33.901 2931 INFO nova.compute.manager"
const testContext = "[req-8e64797b-fb99-4c8a-87e5-9a8de673412f user project - - -]"
const testInstance = "[instance: a445709b-6ad0-40ec-8860-bec60b6ca0c2]"

func TestParseOptionalContextAndFailures(t *testing.T) {
	p := Parser{Location: time.UTC}
	for _, tt := range []struct {
		name, raw, status, message string
		hasContext                 bool
	}{
		{"normal", testHeader + " " + testContext + " " + testInstance + " VM Started (Lifecycle Event)", "ok", testInstance + " VM Started (Lifecycle Event)", true},
		{"traceback", testHeader + "   File \"worker.py\", line 1, in run", "ok", "  File \"worker.py\", line 1, in run", false},
		{"empty body", testHeader, "ok", "", false},
		{"empty context body", testHeader + " [-] ", "ok", "", true},
		{"empty line", "", "empty", "", false},
		{"bad header", "not an OpenStack record", "unparsed", "not an OpenStack record", false},
		{"bad context", testHeader + " [req-broken", "partial", "[req-broken", false},
		{"bad timestamp", strings.Replace(testHeader, "2017-05-14", "2017-99-99", 1) + " hello", "partial", "hello", false},
	} {
		t.Run(tt.name, func(t *testing.T) {
			e := p.Parse(tt.raw, "\n", "file.log", strings.Repeat("a", 64), "test", 1)
			if e.ParseStatus != tt.status || e.Message != tt.message || (e.ContextRaw != nil) != tt.hasContext {
				t.Fatalf("unexpected parse: %+v", e)
			}
			if e.RawText != tt.raw || e.Host != nil {
				t.Fatal("raw text changed or hostname inferred")
			}
			if tt.name == "bad timestamp" && e.EventTime != nil {
				t.Fatal("invented event time")
			}
		})
	}
}

func TestDurationsAndHTTP(t *testing.T) {
	p := Parser{Location: time.UTC}
	for _, tt := range []struct {
		text  string
		value float64
		kind  string
	}{
		{"Took 51.59 seconds to build instance.", 51.59, "build"},
		{"Took 50.72 seconds to spawn the instance on the hypervisor.", 50.72, "spawn"},
		{"Took 1.03 seconds to destroy the instance on the hypervisor.", 1.03, "destroy"},
	} {
		e := p.Parse(testHeader+" "+testContext+" "+testInstance+" "+tt.text, "", "a.log", "hash", "test", 5)
		v := map[string]*float64{"build": e.BuildDuration, "spawn": e.SpawnDuration, "destroy": e.DestroyDuration}[tt.kind]
		if v == nil || *v != tt.value || e.InstanceID == nil || e.RequestID == nil {
			t.Fatalf("lost duration/identity: %+v", e)
		}
	}
	raw := testHeader + " [-] 10.11.10.1 \"GET /v2/project/servers/a445709b-6ad0-40ec-8860-bec60b6ca0c2 HTTP/1.1\" status: 404 len: 99 time: 0.2477829"
	e := p.Parse(raw, "\n", "a.log", "hash", "test", 1)
	if e.HTTPStatus == nil || *e.HTTPStatus != 404 || e.HTTPDuration == nil || *e.HTTPDuration != 0.2477829 || *e.HTTPBytes != 99 {
		t.Fatalf("HTTP fields: %+v", e)
	}
	if e.InstanceID != nil || e.ParseStatus != "ok" {
		t.Fatal("HTTP URL/status should not imply an explicit instance or parsing failure")
	}
}

func TestResourcesAndExplicitHost(t *testing.T) {
	p := Parser{Location: time.UTC}
	for _, tt := range []struct {
		text, key string
		want      float64
	}{
		{"Attempting claim: memory 2048 MB, disk 20 GB, vcpus 1 CPU", "claim_memory_mb", 2048},
		{"Total memory: 64172 MB, used: 512.00 MB", "memory_used_mb", 512},
		{"memory limit: 96258.00 MB, free: 95746.00 MB", "memory_free_mb", 95746},
		{"Total usable vcpus: 16, total allocated vcpus: 1", "allocated_vcpus", 1},
		{"Final resource view: name=compute.example phys_ram=64172MB used_ram=2560MB phys_disk=15GB used_disk=20GB total_vcpus=16 used_vcpus=1 pci_stats=[]", "used_disk_gb", 20},
	} {
		e := p.Parse(testHeader+" [-] "+tt.text, "\n", "a.log", "hash", "test", 1)
		if got, ok := e.Parameters[tt.key]; !ok || got != tt.want {
			t.Fatalf("%s: %v", tt.text, e.Parameters)
		}
		if strings.HasPrefix(tt.text, "Final resource") && (e.Host == nil || *e.Host != "compute.example") {
			t.Fatal("explicit resource hostname was lost")
		}
	}
}

func TestTimezoneAndStableIdentity(t *testing.T) {
	loc := time.FixedZone("test+03", 3*60*60)
	p := Parser{Location: loc}
	a := p.Parse(testHeader+" hello", "\n", "one.log", "sourcehash", "one", 17)
	b := p.Parse(testHeader+" hello", "\n", "moved.log", "sourcehash", "two", 17)
	if *a.EventTime != "2017-05-14T18:43:33.901Z" || *a.TimestampRaw != "2017-05-14 21:43:33.901" {
		t.Fatalf("wrong time: %+v", a)
	}
	if a.EventID != b.EventID || a.EventID == EventID("sourcehash", 18) {
		t.Fatal("event identity depends on path/dataset or ignores line")
	}
}
