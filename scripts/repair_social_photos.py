"""Create a photo-only corrected social review without changing approved copy."""

import argparse
import copy
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from social_completion import locked_week as completed_week, require_unfinished
import prepare_social_review as social
from social_review_delivery import ARTIFACT, review_html
from validate_social_package import validate


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "config/social-photo-repair-2026-W48.json"


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def needed(plan, state):
    if completed_week(ROOT, plan["publication_week"], state):
        return False, None
    entry = state.get("editions", {}).get(plan["source_edition"])
    if not entry or entry.get("publication_week") != plan["publication_week"]:
        raise ValueError("The original edition receipt is missing or mismatched")
    if int(entry.get("review_revision", 1)) >= plan["revision"]:
        return False, None
    if entry.get("artifact_url") != plan["baseline_artifact_url"]:
        raise ValueError("The pending artifact changed; refusing to repair stale bytes")
    match = ARTIFACT.fullmatch(entry["artifact_url"])
    if not match or match[1] != str(entry.get("run_id")):
        raise ValueError("Invalid original social artifact receipt")
    return True, match


def produce(folder, output, plan, *, verify_destinations=True):
    require_unfinished(ROOT, plan["publication_week"])
    raw = (folder / "batch.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != plan["baseline_batch_sha256"]:
        raise ValueError("Repair input is not the exact audited original batch")
    baseline = json.loads(raw)
    if (baseline.get("publishing_week") != plan["publication_week"] or
            baseline.get("source_edition") != plan["source_edition"]):
        raise ValueError("Repair cannot move content to a different edition")

    topics = copy.deepcopy(baseline["topics"])
    news_paths = [topic["path"] for topic in topics if topic["kind"] == "News"]
    if news_paths != plan["expected_news_paths"]:
        raise ValueError("The audited News selection changed")
    if len(news_paths) != 14 or len({topic["id"] for topic in topics}) != 15:
        raise ValueError("The complete 14-News plus one-Research review is required")

    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(folder, output)
    shutil.rmtree(output / "sources", ignore_errors=True)
    (output / "sources").mkdir()
    (output / "assets").mkdir(exist_ok=True)

    history = read(ROOT / "config/social-photo-history.json")
    photos = social.new_photos(topics, history, output, plan["source_edition"])
    if len(photos) != 14 or len({photo["sha256"] for photo in photos.values()}) != 14:
        raise ValueError("Fourteen distinct replacement photographs are required")
    social.render(topics, photos, output)

    batch = copy.deepcopy(baseline)
    batch["topics"] = topics
    batch["review_revision"] = plan["revision"]
    batch["supersedes_batch_sha256"] = plan["baseline_batch_sha256"]
    batch["repair_scope"] = "photographs_and_derived_media_only"
    for item in batch["items"]:
        topic = next(topic for topic in topics if topic["id"] == item["topic_id"])
        item["photo_rights"] = photos.get(topic.get("photo"))

    errors = validate(batch)
    if errors:
        raise ValueError("\n".join(errors))
    checks = social.verify_links(batch) if verify_destinations else {
        "all_ok": False,
        "test_only": True,
    }
    social.review(batch, output)
    save(output / "batch.json", batch)
    save(output / "topics.json", topics)
    save(output / "PHOTO_MANIFEST.json", photos)
    save(output / "LINK_CHECK.json", checks)
    after_sha = hashlib.sha256((output / "batch.json").read_bytes()).hexdigest()
    save(output / "REPAIR_CHANGELOG.json", {
        "review_revision": plan["revision"],
        "before_batch_sha256": plan["baseline_batch_sha256"],
        "after_batch_sha256": after_sha,
        "repair_reason": plan["repair_reason"],
        "copy_destinations_and_schedule_preserved": True,
        "changed_topic_ids": [topic["id"] for topic in topics if topic["kind"] == "News"],
    })
    if checks.get("all_ok"):
        save(output / "READY_FOR_REVIEW.json", {
            "status": social.STATUS,
            "publication_week": plan["publication_week"],
            "review_revision": plan["revision"],
            "editorial_review_required": True,
            "visual_review_complete": True,
            "live_destinations_checked": True,
            "created_at": datetime.now(social.ZONE).isoformat(),
        })
    run_url = "https://github.com/kedmahamelberg-ai/aieo-brief/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "0")
    (output / "BATCH_REVIEW.html").write_text(
        review_html(batch, output, run_url, review_url=run_url)
    )
    return batch


def record(output, plan):
    require_unfinished(ROOT, plan["publication_week"])
    ready = read(output / "READY_FOR_REVIEW.json")
    if (ready.get("review_revision") != plan["revision"] or
            ready.get("visual_review_complete") is not True or
            ready.get("live_destinations_checked") is not True):
        raise ValueError("Only the fully checked photo correction can be recorded")
    artifact_url = os.environ["SOCIAL_ARTIFACT_URL"]
    if not ARTIFACT.fullmatch(artifact_url):
        raise ValueError("Invalid corrected artifact URL")

    state_path = ROOT / "data/social-production/state.json"
    state = read(state_path)
    prior = copy.deepcopy(state["editions"][plan["source_edition"]])
    if prior.get("artifact_url") != plan["baseline_artifact_url"]:
        raise ValueError("The pending artifact changed while the repair ran")
    state.setdefault("review_history", {}).setdefault(plan["source_edition"], []).append(prior)
    digest = hashlib.sha256((output / "batch.json").read_bytes()).hexdigest()
    state["editions"][plan["source_edition"]] = {
        "publication_week": plan["publication_week"],
        "status": social.STATUS,
        "artifact_url": artifact_url,
        "run_id": os.environ["GITHUB_RUN_ID"],
        "review_revision": plan["revision"],
        "batch_sha256": digest,
        "created_at": datetime.now(social.ZONE).isoformat(),
        "supersedes_artifact_url": prior["artifact_url"],
    }

    approval_path = ROOT / "data/social-production/approved" / (plan["publication_week"] + ".json")
    if approval_path.exists():
        approval = read(approval_path)
        history_path = (ROOT / "data/social-production/approval-history" /
                        plan["publication_week"] / (approval["batch_sha256"] + ".json"))
        save(history_path, approval)
        approval.update(
            status="SUPERSEDED_PENDING_CORRECTED_REVIEW",
            corrected_batch_sha256=digest,
            corrected_artifact_url=artifact_url,
            superseded_at=datetime.now(social.ZONE).isoformat(),
        )
        save(approval_path, approval)
    save(state_path, state)

    history_path = ROOT / "config/social-photo-history.json"
    history = read(history_path)
    for photo in read(output / "PHOTO_MANIFEST.json").values():
        for field, key in (("source_url", "source_urls"), ("sha256", "sha256")):
            history[key] = sorted(set(history[key] + [photo[field]]))
    save(history_path, history)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "produce", "record"))
    parser.add_argument("--input", type=Path, default=ROOT / "original-social-review")
    parser.add_argument("--output", type=Path, default=ROOT / "social-review")
    args = parser.parse_args()
    plan = read(PLAN)
    if args.action == "plan":
        pending, match = needed(plan, read(ROOT / "data/social-production/state.json"))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("needed=" + str(pending).lower() + "\n")
                if pending:
                    stream.write("run_id=" + match[1] + "\n")
                    stream.write("artifact_id=" + match[2] + "\n")
        print(json.dumps({"repair_needed": pending, "revision": plan["revision"]}))
    elif args.action == "produce":
        produce(args.input.resolve(), args.output.resolve(), plan)
    else:
        record(args.output.resolve(), plan)


if __name__ == "__main__":
    main()
