"""Replay the existing NYC classifier with its original feature and quality gates."""

import json

import joblib
import numpy as np
import pandas as pd


class Provider:
    def __init__(self, root):
        data = root / "data/processed"
        self.features = json.loads((data / "features.json").read_text())
        quality = {q["site"]: q for q in json.loads((data / "quality.json").read_text())}
        self.frames, self.metadata = {}, {}
        # Allowlist prevents target columns from ever entering the inference frame.
        for site in json.loads((data / "sites.json").read_text()):
            if not quality[site["id"]]["rows_by_split"].get("4", 0):
                continue
            frame = pd.read_parquet(
                data / f"{site['id']}.parquet", columns=["time_ns", "split", *self.features]
            )
            valid = (
                (frame.split == 4)
                & frame.depth_m.ge(0)
                & frame.depth_m.lt(0.05)
                & frame.depth_age_minutes.between(0, 10)
                & frame.depth_coverage_3h.ge(0.8)
                & frame.rain_age_n1.between(15, 105)
                & frame.rain_counter_mm_n1.notna()
            )
            frame = frame[valid].sort_values("time_ns").set_index("time_ns")
            if not frame.empty:
                frame["day"] = pd.to_datetime(frame.index, utc=True).strftime("%Y-%m-%d")
                self.frames[site["id"]] = frame
                self.metadata[site["id"]] = {
                    "id": site["id"],
                    "name": site["name"],
                    "days": sorted(frame.day.unique().tolist()),
                }
        self.models = {h: joblib.load(root / f"artifacts/warning_{h}.joblib") for h in (30, 60)}
        self.policy = json.loads((root / "artifacts/shadow_policy.json").read_text())
        # Existing illustrative example; selected retrospectively, not a new blind evaluation.
        self.default = {
            "site_id": "ugliest_cyan_elephant",
            "day": "2023-08-10",
            "origin": "2023-08-10T19:45:00+00:00",
        }

    def sites(self):
        return list(self.metadata.values())

    def frame(self, site):
        if site not in self.frames:
            raise ValueError("Điểm chưa có dữ liệu kiểm thử FloodNet hợp lệ.")
        return self.frames[site]

    def times(self, site, day):
        frame = self.frame(site)
        return [
            {
                "id": pd.Timestamp(t, tz="UTC").isoformat(),
                "label": pd.Timestamp(t, tz="UTC").strftime("%H:%M UTC"),
            }
            for t in frame[frame.day == day].index
        ]

    def feature_row(self, site, origin):
        ts = pd.Timestamp(origin)
        if pd.isna(ts) or ts.tzinfo is None:
            raise ValueError("Thời điểm phải có múi giờ.")
        frame = self.frame(site)
        if ts.value not in frame.index:
            raise ValueError("Không có cửa sổ dưới ngưỡng ngập đủ chất lượng tại thời điểm này.")
        row = frame.loc[ts.value, self.features]
        x = row.to_numpy(dtype="float32").reshape(1, -1)
        if np.isinf(x).any():
            raise ValueError("Đặc trưng chứa giá trị vô hạn.")
        return row, x, ts.tz_convert("UTC").isoformat()

    def predict(self, site, origin):
        row, x, origin = self.feature_row(site, origin)
        horizons = []
        for h, bundle in self.models.items():
            p = bundle["model"].predict_proba(x)[0, 1]
            score = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
            probability = float(bundle["calibration"].predict_proba([[score]])[0, 1])
            threshold = self.policy["horizons"][str(h)]["threshold"]
            horizons.append(
                {
                    "minutes": h,
                    "value": probability,
                    "shadow_review_threshold": threshold,
                    "shadow_review_candidate": probability >= threshold,
                }
            )
        return {
            "status": "research_only",
            "site_id": site,
            "origin": origin,
            "current": {"value": float(row.depth_m), "unit": "m"},
            "horizons": horizons,
            "horizon_probabilities_consistent": horizons[0]["value"] <= horizons[1]["value"],
            "history": [],
            "depth_forecast_m": None,
            "input_summary": {
                "features": len(self.features),
                "depth_age_minutes": float(row.depth_age_minutes),
                "depth_coverage_3h": float(row.depth_coverage_3h),
                "rain_age_minutes": float(row.rain_age_n1),
                "last_input_origin": origin,
            },
        }
