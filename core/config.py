from pathlib import Path
import tomllib


def load_config(path="config/defaults.toml"):
    config_path = Path(path)

    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("rb") as f:
        return tomllib.load(f)
