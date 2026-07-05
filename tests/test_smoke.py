import os
import subprocess


def test_readme_exists():
    assert os.path.isfile("README.md")


def test_gitignore_exists():
    assert os.path.isfile(".gitignore")


def test_csv_not_tracked():
    result = subprocess.run(
        ["git", "ls-files", "resultados_cam.csv"],
        capture_output=True, text=True
    )
    assert result.stdout.strip() == "", f"CSV still tracked: {result.stdout.strip()}"
