TEST FIXTURE
NOT A REAL SRTM TILE

Synthetic 3x3 big-endian int16 samples, north row first:

```text
100  200     300
  0 -32768    30
-10   20      40
```

Explicit fixture tile: N21E105.hgt. Sample spacing: 0.5 degrees.
Northwest sample: (22, 105); southeast: (21, 106).
-32768 is nodata. No real observation time or vertical datum is claimed.
