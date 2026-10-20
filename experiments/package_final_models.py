"""Explicit allowlist packaging: code/aggregate results separate from private models."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = "artifacts/ml-models/final-2026-10-20-v3"
RESULT_DIRS = ["final-consultation-2026-10-20-v3", "final-scheduling-2026-10-20-v2",
    "final-artifact-verification-2026-10-20-v3", "final-model-analysis-2026-10-20-v3",
    "final-model-checks-2026-10-20-v1"]
SOURCES = ["prediction/duration_features.py", "prediction/surgery_duration.py", "prediction/los_model.py", "prediction/consultation_features.py",
    "prediction/prediction_planning.py", "tests/test_final_models.py", "experiments/train_consultation_models.py",
    "experiments/final_prediction_scheduling.py", "experiments/verify_final_models.py",
    "experiments/run_final_model_checks.py", "experiments/summarize_final_models.py",
    "experiments/package_final_models.py", "experiments/final_model_requirements.txt",
    "FINAL_MODEL_IMPROVEMENTS.md", "FINAL_MODEL_RESULTS_FOR_REPORT.md"]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/"artifacts/submission"):
        parser.error("Use the ignored artifacts/submission directory")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Output must be new or empty")
    new_files = list(SOURCES)
    for directory in RESULT_DIRS:
        folder = ROOT/"experiments/results"/directory
        new_files.extend(p.relative_to(ROOT).as_posix() for p in folder.iterdir() if p.is_file())
    model_manifest = json.loads((ROOT/"experiments/results/final-consultation-2026-10-20-v3/manifest.json").read_text())
    if model_manifest.get("status") != "complete":
        raise ValueError("Incomplete training campaign")
    for name, expected in model_manifest["source_sha256"].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f"Training/inference source changed: {name}")
    original = ROOT.parent/"IA-et-Sante-groupe-2"
    inputs={"room_data":original/"resources/model_surgery_duration_dataset.parquet",
            "los_data":original/"resources/model_los_dataset.parquet",
            "old_room":original/"results/surgery_duration_model.joblib"}
    for name,path in inputs.items():
        if digest(path) != model_manifest["input_sha256"][name]:
            raise ValueError("Original input/model changed since training")
    model_files = sorted(f"{MODEL_DIR}/{name}" for name in model_manifest["artifact_sha256"])
    for name, expected in model_manifest["artifact_sha256"].items():
        if digest(ROOT/MODEL_DIR/name) != expected:
            raise ValueError("Model artifact hash mismatch")
    (ROOT/"FINAL_MODEL_ARTIFACT_FILES.txt").write_text("\n".join(model_files)+"\n", encoding="utf-8")
    new_files += ["FINAL_MODEL_SUBMISSION_FILES.txt", "FINAL_MODEL_ARTIFACT_FILES.txt"]
    new_files = sorted(set(new_files))
    (ROOT/"FINAL_MODEL_SUBMISSION_FILES.txt").write_text("\n".join(new_files)+"\n", encoding="utf-8")
    previous = (ROOT/"experiments/COMMIT_FILES.txt").read_text(encoding="utf-8-sig").splitlines()
    files = sorted(set(new_files+previous))
    for name in files:
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError("Invalid allowlisted source path")
        if any(piece in ("resources", ".deps", ".venv", ".git", "__pycache__") for piece in Path(name).parts):
            raise ValueError("Confidential/environment path in source package")
        if path.suffix.lower() in (".parquet", ".xlsx", ".joblib", ".env", ".pem"):
            raise ValueError("Data/credential/model excluded from code package")
    compiled = []
    for name in files:
        if name.endswith(".py"):
            compile((ROOT/name).read_text(encoding="utf-8-sig"), name, "exec")
            compiled.append(name)
    checks = json.loads((ROOT/"experiments/results/final-model-checks-2026-10-20-v1/verification.json").read_text())
    if any(item["exit_code"] != 0 for item in checks["checks"]):
        raise ValueError("Failed final check")
    log = (ROOT/"experiments/results/final-model-checks-2026-10-20-v1/regression.txt").read_text()
    count = int(re.search(r"Ran (\d+) tests", log).group(1))
    skipped = int(re.search(r"OK \(skipped=(\d+)\)", log).group(1))
    runs = pd.read_csv(ROOT/"experiments/results/final-scheduling-2026-10-20-v2/scheduling_runs.csv")
    if (len(runs) != 64 or not runs.evaluations.eq(500).all() or runs.failures.sum()
            or runs.search_deadline_stops.sum() or not runs.cases.eq(runs.completed+runs.unstarted).all()):
        raise ValueError("Scheduling campaign verification failed")
    for _, group in runs.groupby(["cohort","rooms","solver_seed"]):
        if set(group.arm) != {"median","ml"} or len(group) != 2 or group.cases.nunique()!=1:
            raise ValueError("Unpaired scheduling run")
    diff = subprocess.run(["git","diff","--check"],cwd=ROOT,capture_output=True,text=True)
    if diff.returncode:
        raise ValueError("git diff --check failed")
    hashes = {name:digest(ROOT/name) for name in files}
    source_zip=output/"s1s2-and-final-model-code-results.zip"
    with ZipFile(source_zip,"x",compression=ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(ROOT/name,name)
        archive.writestr("SUBMISSION_PACKAGE_README.txt",
            "Overlay these files on the existing project checkout; this is not a standalone repository.\n"
            "Includes previous synthetic S1/S2 evidence and final aggregate model results.\n"
            "No patient records, real schedules, model weights, environments or credentials included.\n"
            "See FINAL_MODEL_IMPROVEMENTS.md for executed checks, limitations and reproduction.\n")
    model_zip=output/"PRIVATE-versioned-models.zip"
    with ZipFile(model_zip,"x",compression=ZIP_DEFLATED) as archive:
        for name in model_files:
            archive.write(ROOT/name,name)
        archive.writestr("PRIVATE_MODEL_NOTICE.txt",
            "Private project artifacts trained on authorized hospital data.\n"
            "Contains fitted weights and train-derived categorical/median statistics; not deidentified raw data.\n"
            "Keep out of public Git; include only in the authorized private submission.\n"
            "No default model replacement is performed. See the separate code/results report.\n")
    for path in (source_zip,model_zip):
        with ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity failure")
    audit = {"status":"complete", "source_files":len(files), "new_model_task_files":len(new_files),
        "compiled_python_files":len(compiled),"tests_run":count,"tests_passed":count-skipped,"tests_skipped":skipped,
        "scheduling_runs":len(runs),"scheduling_evaluations":int(runs.evaluations.sum()),
        "all_source_hashes":hashes,"model_hashes":{name:digest(ROOT/name) for name in model_files},
        "zip_sha256":{p.name:digest(p) for p in (source_zip,model_zip)},
        "git_diff_check_exit":diff.returncode,"confidential_records_exported":False,
        "original_training_inputs_and_or_artifact_unchanged":True,
        "git_branch":subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
        "model_handling":"Separate private package; excluded from code ZIP and public Git"}
    (output/"SUBMISSION_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in audit.items() if k not in ("all_source_hashes","model_hashes")},indent=2))


if __name__ == "__main__":
    main()
