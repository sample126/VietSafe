"""SMAP soil-moisture interchange boundary; no native HDF5/NetCDF decoding."""

from .environment_json import grid_cli, read_grid


def read_smap(path):
    return read_grid(path, "smap")


def main(argv=None):
    grid_cli(read_smap, "Offline SMAP normalized JSON (not native NASA granules)", argv)


if __name__ == "__main__":
    main()
