import { describe, it, expect } from "vitest";
import {
  VIDEO_STATUS_META,
  CLIP_STATUS_META,
  ACTIVE_VIDEO_STATUSES,
  STAGE_PENDING_STATUSES,
  stagePendingCount,
  type VideoStatus,
  type ClipStatus,
} from "./status-labels";

describe("VIDEO_STATUS_META", () => {
  it("has entries for all expected video statuses", () => {
    const expected: VideoStatus[] = [
      "discovered",
      "triage_metadata_passed",
      "triage_metadata_rejected",
      "on_hold_metadata_passed",
      "triage_caption_passed",
      "triage_caption_rejected",
      "triage_caption_skipped",
      "downloading",
      "downloaded",
      "transcribing",
      "transcribed",
      "transcribe_error",
      "triage_transcript_passed",
      "triage_transcript_rejected",
      "approved_for_clips",
      "finding_clips",
      "clips_found",
      "processing_error",
    ];
    for (const s of expected) {
      expect(VIDEO_STATUS_META[s]).toBeDefined();
      expect(VIDEO_STATUS_META[s].label).toBeTruthy();
    }
  });

  it("each entry has label, color, active", () => {
    for (const [, meta] of Object.entries(VIDEO_STATUS_META)) {
      expect(meta.label).toBeTruthy();
      expect(meta.color).toMatch(/^#/);
      expect(typeof meta.active).toBe("boolean");
    }
  });

  it("downloading is marked active", () => {
    expect(VIDEO_STATUS_META.downloading.active).toBe(true);
  });

  it("discovered is not active", () => {
    expect(VIDEO_STATUS_META.discovered.active).toBe(false);
  });
});

describe("CLIP_STATUS_META", () => {
  it("has entries for all expected clip statuses", () => {
    const expected: ClipStatus[] = [
      "identified",
      "editing",
      "edited",
      "thumbnail_ready",
      "metadata_ready",
      "uploading_youtube",
      "scheduled_youtube",
      "uploaded_youtube",
      "rejected_youtube",
      "deleted_youtube",
      "unscheduled_youtube",
      "pending_tiktok_manual",
      "uploaded_tiktok",
      "processing_error",
    ];
    for (const s of expected) {
      expect(CLIP_STATUS_META[s]).toBeDefined();
      expect(CLIP_STATUS_META[s].label).toBeTruthy();
    }
  });

  it("metadata_ready shows pending review label", () => {
    expect(CLIP_STATUS_META.metadata_ready.label).toContain("Revisão");
  });
});

describe("ACTIVE_VIDEO_STATUSES", () => {
  it("contains active statuses", () => {
    expect(ACTIVE_VIDEO_STATUSES.has("downloading")).toBe(true);
    expect(ACTIVE_VIDEO_STATUSES.has("transcribing")).toBe(true);
    expect(ACTIVE_VIDEO_STATUSES.has("finding_clips")).toBe(true);
  });

  it("does not contain inactive statuses", () => {
    expect(ACTIVE_VIDEO_STATUSES.has("discovered")).toBe(false);
    expect(ACTIVE_VIDEO_STATUSES.has("processing_error")).toBe(false);
  });
});

describe("stagePendingCount", () => {
  const summary: Record<string, number> = {
    discovered: 3,
    triage_metadata_passed: 5,
    metadata_ready: 2,
    unscheduled_youtube: 1,
  };

  it("returns sum for triage_metadata stage", () => {
    expect(stagePendingCount(summary, "triage_metadata")).toBe(3);
  });

  it("returns sum for upload_youtube stage", () => {
    expect(stagePendingCount(summary, "upload_youtube")).toBe(3); // 2+1
  });

  it("returns 0 for discover stage (no pending statuses)", () => {
    expect(stagePendingCount(summary, "discover")).toBe(0);
  });

  it("returns 0 for unknown stage", () => {
    expect(stagePendingCount(summary, "nonexistent")).toBe(0);
  });

  it("handles missing status keys gracefully", () => {
    expect(stagePendingCount({}, "triage_metadata")).toBe(0);
  });
});

describe("STAGE_PENDING_STATUSES", () => {
  it("has entries for all pipeline stages", () => {
    const stages = [
      "discover",
      "triage_metadata",
      "triage_caption",
      "download",
      "transcribe",
      "triage_transcript",
      "find_clips",
      "edit",
      "thumbnail",
      "generate_metadata",
      "upload_youtube",
      "upload_tiktok",
      "sync_youtube",
    ];
    for (const s of stages) {
      expect(STAGE_PENDING_STATUSES[s]).toBeDefined();
    }
  });
});
