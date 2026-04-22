import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI(title="TrailCam Viewer API")

PREDICTIONS_FILE = os.environ.get(
    "PREDICTIONS_FILE",
    r"C:\Users\dabea\Downloads\Photos-3-001\predictions.json",
)


def parse_label(label_str: str) -> dict:
    """Parse 'uuid;class;order;family;genus;species;common_name' into a dict."""
    parts = label_str.split(";")
    common_name = parts[-1] if parts else label_str
    scientific = ""
    if len(parts) >= 6 and parts[4] and parts[5]:
        scientific = f"{parts[4].capitalize()} {parts[5]}"
    elif len(parts) >= 2 and parts[1]:
        scientific = parts[1].capitalize()
    return {
        "id": parts[0],
        "common_name": common_name,
        "scientific": scientific,
        "raw": label_str,
    }


def load_predictions() -> list:
    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    result = []
    for pred in data["predictions"]:
        filepath = pred["filepath"]
        filename = Path(filepath).name

        prediction_label = None
        if "prediction" in pred:
            prediction_label = parse_label(pred["prediction"])

        top5 = []
        if "classifications" in pred:
            for cls, score in zip(
                pred["classifications"]["classes"],
                pred["classifications"]["scores"],
            ):
                top5.append({**parse_label(cls), "score": round(score, 4)})

        result.append({
            "filepath": filepath,
            "filename": filename,
            "prediction": prediction_label,
            "prediction_score": pred.get("prediction_score"),
            "prediction_source": pred.get("prediction_source"),
            "top5": top5,
            "detections": pred.get("detections", []),
            "model_version": pred.get("model_version"),
            "failures": pred.get("failures", []),
            "country": pred.get("country"),
            "latitude": pred.get("latitude"),
            "longitude": pred.get("longitude"),
        })

    return result


@app.get("/api/predictions")
def get_predictions():
    return {"predictions": load_predictions()}


@app.get("/api/image")
def get_image(path: str = Query(...)):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/preview")
def get_preview(path: str = Query(...)):
    # Preview filenames encode the full path: C:/foo/bar.jpg → C~~foo~bar.jpg
    preview_dir = str(Path(path).parent / "previews")
    encoded = path.replace(":", "~").replace("/", "~").replace("\\", "~")
    preview_path = os.path.join(preview_dir, f"anno_{encoded}")
    if not os.path.isfile(preview_path):
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path, media_type="image/jpeg")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
