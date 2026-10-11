"""Frozen HGB neighbour inference; source speed units are unverified."""

import joblib
import numpy as np
import pandas as pd


class Provider:
    def __init__(self, root):
        df = pd.read_csv(root / "source/data__sz_speed.csv")
        self.names = df.columns.tolist()
        self.raw = df.to_numpy(dtype="float32")
        self.mask = np.isfinite(self.raw) & (self.raw > 0)
        a = pd.read_csv(root / "source/data__sz_adj.csv", header=None).to_numpy(dtype="float32")
        observed = np.where(self.mask, self.raw, np.nan)
        train = observed[:1920]
        self.known = self.mask[:1920].any(0)
        mu, sigma = float(np.nanmean(train)), float(np.nanstd(train))
        med = np.nan_to_num(np.nanmedian(train, axis=0), nan=float(np.nanmedian(train)))
        context = np.stack((np.nanmean(train, axis=0), np.nanstd(train, axis=0)), axis=1)
        context[:, 0] = (context[:, 0] - mu) / sigma
        context[:, 1] /= sigma
        self.context = np.nan_to_num(context).astype("float32")
        filled = np.zeros_like(self.raw)
        for start, stop in ((0, 1920), (1920, 2400), (2400, 2976)):
            filled[start:stop] = (
                pd.DataFrame(observed[start:stop])
                .ffill(limit=4)
                .fillna(dict(enumerate(med)))
                .to_numpy()
            )
        self.x = np.stack(((filled - mu) / sigma, self.mask.astype("float32")), -1)
        support = ((a + np.eye(156, dtype="float32")).T > 0).astype("float32")
        np.fill_diagonal(support, 0)
        count = self.mask.astype("float32") @ support.T
        summed = np.where(self.mask, self.raw, 0) @ support.T
        degree = support.sum(1)
        fallback = (filled @ support.T) / np.maximum(degree, 1)
        mean = np.divide(summed, count, out=fallback.copy(), where=count > 0)
        mean[:, degree == 0] = filled[:, degree == 0]
        self.neighbours = np.stack(((mean - mu) / sigma, count / np.maximum(degree, 1)), -1).astype(
            "float32"
        )
        self.models = joblib.load(root / "results/HGB_neighbours_l31_i240.joblib")
        self.default = {"site_id": "90217", "day": "test", "origin": "2411"}

    def sites(self):
        return [
            {"id": name, "name": f"Đoạn {name}", "days": ["test"]}
            for i, name in enumerate(self.names)
            if self.known[i]
        ]

    def check_site(self, site):
        if site not in self.names or not self.known[self.names.index(site)]:
            raise ValueError("Đoạn chưa có dữ liệu huấn luyện SZ-Taxi.")
        return self.names.index(site)

    def times(self, site, day):
        self.check_site(site)
        return (
            [{"id": str(i), "label": f"Dòng {i} · khoảng 15 phút"} for i in range(2411, 2972)]
            if day == "test"
            else []
        )

    def features(self, index):
        lag = np.arange(index - 11, index + 1)
        return np.concatenate(
            (
                self.x[lag].transpose(1, 0, 2).reshape(156, -1),
                self.context,
                self.neighbours[lag].transpose(1, 0, 2).reshape(156, -1),
            ),
            axis=-1,
        ).astype("float32")

    def predict(self, site, origin):
        node = self.check_site(site)
        if not origin.isdecimal() or not 2411 <= int(origin) < 2972:
            raise ValueError("Chỉ số dòng phải thuộc tập kiểm thử 2411–2971.")
        index = int(origin)
        x = self.features(index)
        y = np.maximum(np.stack([model.predict(x) for model in self.models], axis=-1), 0)
        current = float(self.raw[index, node]) if self.mask[index, node] else None
        return {
            "status": "research_only",
            "site_id": site,
            "origin": str(index),
            "origin_utc": None,
            "current": {"value": current, "unit": "source_speed_scale"},
            "horizons": [
                {"minutes": h, "value": float(y[node, k])} for k, h in enumerate((15, 30, 60))
            ],
            "history": [
                {
                    "offset_minutes": int((i - index) * 15),
                    "value": float(self.raw[i, node]) if self.mask[i, node] else None,
                }
                for i in range(index - 11, index + 1)
            ],
            "input_summary": {
                "history_steps": 12,
                "step_minutes": 15,
                "features": x.shape[1],
                "observed_fraction": float(self.mask[index - 11 : index + 1, node].mean()),
                "missing_policy": "ffill ≤ 4 bước trong mỗi split, sau đó trung vị tập train",
                "last_input_row": index,
            },
        }
