package openstack

import (
	"crypto/sha256"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"
	"time"

	"logparser/internal/model"
)

const uuid = `[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}`
const number = `([0-9]+(?:\.[0-9]+)?)`

var (
	header        = regexp.MustCompile(`^(\S+) (\S+) (\S+) (\d+) (\S+) (\S+)(?: (.*))?$`)
	context       = regexp.MustCompile(`^\[(?:req-[^\]]*|-)\](?: |$)`)
	request       = regexp.MustCompile(`^\[(req-` + uuid + `)(?: |\])`)
	instance      = regexp.MustCompile(`\[instance: (` + uuid + `)\]`)
	httpLine      = regexp.MustCompile(`"([A-Z]+) (\S+) HTTP/\d(?:\.\d)?" status: (\d+) len: (\d+) time: (\S+)`)
	build         = regexp.MustCompile(`\bTook ` + number + ` seconds to build instance\.`)
	spawn         = regexp.MustCompile(`\bTook ` + number + ` seconds to spawn the instance on the hypervisor\.`)
	destroy       = regexp.MustCompile(`\bTook ` + number + ` seconds to destroy the instance on the hypervisor\.`)
	claim         = regexp.MustCompile(`Attempting claim: memory ` + number + ` MB, disk ` + number + ` GB, vcpus ` + number + ` CPU`)
	resourceTotal = regexp.MustCompile(`Total (memory|disk|vcpu): ` + number + ` (MB|GB|VCPU), used: ` + number + ` (?:MB|GB|VCPU)`)
	resourceLimit = regexp.MustCompile(`(memory|disk|vcpu) limit: ` + number + ` (MB|GB|VCPU), free: ` + number + ` (?:MB|GB|VCPU)`)
	resourceView  = regexp.MustCompile(`\b(phys_ram|used_ram|phys_disk|used_disk|total_vcpus|used_vcpus)=` + number + `(MB|GB)?\b`)
	usableVCPUs   = regexp.MustCompile(`Total usable vcpus: ` + number + `, total allocated vcpus: ` + number)
	hostView      = regexp.MustCompile(`Final resource view: name=(\S+)`)
)

// Parser never infers a hostname or instance from unrelated identifiers.
type Parser struct{ Location *time.Location }

func EventID(sourceHash string, line uint64) string {
	return fmt.Sprintf("%x", sha256.Sum256([]byte(sourceHash+":"+strconv.FormatUint(line, 10))))
}

func (p Parser) Parse(raw, ending, file, sourceHash, dataset string, line uint64) model.Event {
	e := model.Event{
		SchemaVersion: model.SchemaVersion, ParserVersion: model.ParserVersion,
		EventID: EventID(sourceHash, line), DatasetID: dataset, SourceFile: file,
		SourceSHA256: sourceHash, LineStart: line, LineEnd: line,
		RawText: raw, LineEnding: ending, Message: raw, Timezone: p.Location.String(),
		Parameters: map[string]float64{}, ParseErrors: []string{},
		ParseStatus: "ok", TemplateStatus: "pending",
	}
	if raw == "" {
		e.ParseStatus = "empty"
		return e
	}
	m := header.FindStringSubmatch(raw)
	if m == nil {
		e.ParseStatus = "unparsed"
		e.ParseErrors = append(e.ParseErrors, "invalid_header")
		return e
	}
	e.SourceName, e.Level, e.Component = &m[1], &m[5], &m[6]
	timestamp := m[2] + " " + m[3]
	e.TimestampRaw = &timestamp
	parsed, err := time.ParseInLocation("2006-01-02 15:04:05.999999999", timestamp, p.Location)
	if err != nil {
		e.ParseErrors = append(e.ParseErrors, "invalid_timestamp")
	} else {
		ts := parsed.UTC().Format(time.RFC3339Nano)
		e.EventTime = &ts
	}
	pid, err := strconv.ParseUint(m[4], 10, 64)
	if err != nil {
		e.ParseErrors = append(e.ParseErrors, "invalid_pid")
	} else {
		e.PID = &pid
	}
	e.Message = m[7]
	if c := context.FindString(e.Message); c != "" {
		ctx := strings.TrimSuffix(c, " ")
		e.ContextRaw = &ctx
		if r := request.FindStringSubmatch(ctx); r != nil {
			e.RequestID = &r[1]
		} else if ctx != "[-]" {
			e.ParseErrors = append(e.ParseErrors, "invalid_request_id")
		}
		e.Message = e.Message[len(c):]
	} else if strings.HasPrefix(e.Message, "[req-") || strings.HasPrefix(e.Message, "[-") {
		e.ParseErrors = append(e.ParseErrors, "invalid_context")
	}
	if m := instance.FindStringSubmatch(e.Message); m != nil {
		e.InstanceID = &m[1]
	}
	if m := httpLine.FindStringSubmatch(e.Message); m != nil {
		e.HTTPMethod, e.HTTPURL = &m[1], &m[2]
		status, err := strconv.ParseUint(m[3], 10, 16)
		if err != nil || status < 100 || status > 599 {
			e.ParseErrors = append(e.ParseErrors, "invalid_http_status")
		} else {
			s := uint16(status)
			e.HTTPStatus = &s
		}
		b, err := strconv.ParseUint(m[4], 10, 64)
		if err != nil {
			e.ParseErrors = append(e.ParseErrors, "invalid_http_bytes")
		} else {
			e.HTTPBytes = &b
		}
		e.HTTPDuration = numeric(m[5], &e)
	}
	e.BuildDuration = duration(build, &e)
	e.SpawnDuration = duration(spawn, &e)
	e.DestroyDuration = duration(destroy, &e)
	if m := claim.FindStringSubmatch(e.Message); m != nil {
		for i, key := range []string{"claim_memory_mb", "claim_disk_gb", "claim_vcpus"} {
			parameter(&e, key, m[i+1])
		}
	}
	units := map[string]string{"MB": "mb", "GB": "gb", "VCPU": "count"}
	for _, item := range []struct {
		pattern       *regexp.Regexp
		first, second string
	}{
		{resourceTotal, "total", "used"}, {resourceLimit, "limit", "free"},
	} {
		if m := item.pattern.FindStringSubmatch(e.Message); m != nil {
			parameter(&e, m[1]+"_"+item.first+"_"+units[m[3]], m[2])
			parameter(&e, m[1]+"_"+item.second+"_"+units[m[3]], m[4])
		}
	}
	if m := hostView.FindStringSubmatch(e.Message); m != nil {
		e.Host = &m[1]
		for _, m := range resourceView.FindAllStringSubmatch(e.Message, -1) {
			key := m[1]
			if m[3] != "" {
				key += "_" + strings.ToLower(m[3])
			}
			parameter(&e, key, m[2])
		}
	}
	if m := usableVCPUs.FindStringSubmatch(e.Message); m != nil {
		parameter(&e, "usable_vcpus", m[1])
		parameter(&e, "allocated_vcpus", m[2])
	}
	if len(e.ParseErrors) > 0 {
		seen := map[string]bool{}
		errors := e.ParseErrors[:0]
		for _, code := range e.ParseErrors {
			if !seen[code] {
				errors = append(errors, code)
				seen[code] = true
			}
		}
		e.ParseErrors = errors
		e.ParseStatus = "partial"
	}
	return e
}

func numeric(s string, e *model.Event) *float64 {
	v, err := strconv.ParseFloat(s, 64)
	if err != nil || math.IsNaN(v) || math.IsInf(v, 0) || v < 0 {
		e.ParseErrors = append(e.ParseErrors, "invalid_numeric_parameter")
		return nil
	}
	return &v
}

func duration(re *regexp.Regexp, e *model.Event) *float64 {
	if m := re.FindStringSubmatch(e.Message); m != nil {
		return numeric(m[1], e)
	}
	return nil
}

func parameter(e *model.Event, key, value string) {
	if v := numeric(value, e); v != nil {
		e.Parameters[key] = *v
	}
}
