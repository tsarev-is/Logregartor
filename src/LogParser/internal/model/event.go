package model

const SchemaVersion = 1
const ParserVersion = "1.0.0"

// Event represents one physical source line. Missing fields remain JSON null.
type Event struct {
	SchemaVersion   int                `json:"schema_version"`
	ParserVersion   string             `json:"parser_version"`
	EventID         string             `json:"event_id"`
	DatasetID       string             `json:"dataset_id"`
	SourceFile      string             `json:"source_file"`
	SourceSHA256    string             `json:"source_sha256"`
	LineStart       uint64             `json:"line_start"`
	LineEnd         uint64             `json:"line_end"`
	RawText         string             `json:"raw_text"`
	LineEnding      string             `json:"line_ending"`
	TimestampRaw    *string            `json:"timestamp_raw"`
	EventTime       *string            `json:"event_time"`
	Timezone        string             `json:"timezone_assumption"`
	SourceName      *string            `json:"source_name"`
	PID             *uint64            `json:"pid"`
	Level           *string            `json:"level"`
	Component       *string            `json:"component"`
	ContextRaw      *string            `json:"context_raw"`
	Message         string             `json:"message"`
	RequestID       *string            `json:"request_id"`
	InstanceID      *string            `json:"instance_id"`
	Host            *string            `json:"host"`
	HTTPMethod      *string            `json:"http_method"`
	HTTPURL         *string            `json:"http_url"`
	HTTPStatus      *uint16            `json:"http_status"`
	HTTPDuration    *float64           `json:"http_duration_seconds"`
	HTTPBytes       *uint64            `json:"http_response_bytes"`
	BuildDuration   *float64           `json:"build_duration_seconds"`
	SpawnDuration   *float64           `json:"spawn_duration_seconds"`
	DestroyDuration *float64           `json:"destroy_duration_seconds"`
	Parameters      map[string]float64 `json:"parameters"`
	ParseStatus     string             `json:"parse_status"`
	ParseErrors     []string           `json:"parse_errors"`
	TemplateID      *string            `json:"template_id"`
	TemplateVersion *string            `json:"template_version"`
	TemplateStatus  string             `json:"template_status"`
	IngestionRunID  *string            `json:"ingestion_run_id"`
}
