"""Inference-only adaptation of the frozen 2026-10-07 Bellinge benchmark.

Train-period statistics and feature order exactly match benchmark.Data.tabular(spatial=True).
Saved holdout timestamps select retrospective examples; saved targets/predictions are NOT read.
"""

import joblib
import numpy as np
import pandas as pd


class Provider:
    def __init__(self, root):
        depth = pd.read_parquet(root / "prepared/depth.parquet")
        rain = pd.read_parquet(root / "prepared/rain.parquet")
        self.names = depth.columns.tolist()
        self.index = depth.index
        self.depth = depth.to_numpy()
        self.n = len(self.names)
        train = self.index < "2019-01-01"
        mean = depth.loc[train].mean().to_numpy(dtype="float32")
        std = depth.loc[train].std().clip(lower=0.03).to_numpy(dtype="float32")
        filled = depth.ffill(limit=2).fillna(depth.loc[train].median())
        self.local = ((filled.to_numpy() - mean) / std).astype("float32")
        self.mask = np.isfinite(self.depth).astype("float32")
        self.rainmask = rain.notna().to_numpy(dtype="float32")
        rr = np.log1p(rain.fillna(0).to_numpy())
        rr /= np.maximum(np.std(rr[train], axis=0), 0.01)
        self.rain = np.concatenate((rr, self.rainmask), axis=1).astype("float32")
        day = (self.index.hour * 60 + self.index.minute).to_numpy() / 1440
        year = (self.index.dayofyear.to_numpy() - 1 + day) / 365.25
        self.calendar = np.stack(
            (
                np.sin(2 * np.pi * day),
                np.cos(2 * np.pi * day),
                np.sin(2 * np.pi * year),
                np.cos(2 * np.pi * year),
            ),
            axis=1,
        ).astype("float32")
        with np.load(root / "results/test_predictions.npz", allow_pickle=False) as saved:
            self.anchors = pd.DatetimeIndex(saved["timestamps"])
        self.allowed = set(self.anchors)
        self.days = sorted(set(self.anchors.strftime("%Y-%m-%d")))
        self.models = joblib.load(root / "results/HGB_all_nodes_leaves31_iter240.joblib")
        self.default = {
            "site_id": self.names[0],
            "day": self.days[0],
            "origin": self.anchors[0].isoformat(),
        }

    def sites(self):
        return [{"id": name, "name": name, "days": self.days} for name in self.names]

    def check_site(self, site):
        if site not in self.names:
            raise ValueError("Điểm chưa được huấn luyện/đánh giá trên Bellinge.")
        return self.names.index(site)

    def times(self, site, day):
        self.check_site(site)
        return [
            {"id": t.isoformat(), "label": t.strftime("%H:%M · giờ nguồn")}
            for t in self.anchors[self.anchors.strftime("%Y-%m-%d") == day]
        ]

    def row_index(self, origin):
        ts = pd.Timestamp(origin)
        if pd.isna(ts) or ts.tzinfo is not None:
            raise ValueError(
                "Chọn đúng thời điểm theo đồng hồ dữ liệu Bellinge; chưa quy đổi múi giờ."
            )
        if ts not in self.allowed:
            raise ValueError("Không có cửa sổ kiểm thử hợp lệ tại thời điểm này.")
        return int(self.index.get_loc(ts))

    def features(self, index):
        lag = np.arange(index - 23, index + 1)
        if (
            (self.mask[lag].sum(0) < 22).any()
            or not self.mask[index].all()
            or not self.rainmask[lag].all()
        ):
            raise ValueError("Lịch sử mực nước hoặc mưa không đủ chất lượng.")
        local, mask = self.local[lag].T, self.mask[lag].T
        common = np.concatenate((self.rain[lag].reshape(-1), self.calendar[index]))
        global_history = np.concatenate((local.reshape(-1), mask.reshape(-1)))
        return np.concatenate(
            (
                local,
                mask,
                np.broadcast_to(common, (self.n, len(common))),
                np.eye(self.n, dtype="float32"),
                np.broadcast_to(global_history, (self.n, len(global_history))),
            ),
            axis=1,
        ).astype("float32")

    def predict(self, site, origin):
        node = self.check_site(site)
        index = self.row_index(origin)
        x = self.features(index)
        y = (
            np.stack([model.predict(x) for model in self.models], axis=-1)
            + self.depth[index, :, None]
        )
        return {
            "status": "research_only",
            "site_id": site,
            "origin": self.index[index].isoformat(),
            "origin_utc": None,
            "current": {"value": float(self.depth[index, node]), "unit": "m"},
            "horizons": [
                {"minutes": h, "value": float(y[node, k])} for k, h in enumerate((30, 60))
            ],
            "history": [
                {
                    "offset_minutes": int((i - index) * 5),
                    "value": float(self.depth[i, node]) if self.mask[i, node] else None,
                }
                for i in range(index - 23, index + 1)
            ],
            "input_summary": {
                "history_steps": 24,
                "step_minutes": 5,
                "features": x.shape[1],
                "sensors": self.n,
                "last_input_origin": origin,
            },
        }
