import sys
import os
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
import pytest
import re
from PIL import Image
from pixelmatch.contrib.PIL import pixelmatch


@pytest.fixture
def assert_snapshot(pytestconfig: Any, request: Any, browser_name: str) -> Callable:
    node_name = re.sub(r'-(\d+)', '', request.node.name)
    test_name = f"{str(Path(node_name))}[{str(sys.platform)}]"
    test_dir = str(Path(request.node.name)).split('[', 1)[0]

    def compare(img: bytes, *, threshold: float = 0.9, current_tab_name: str, fail_fast=False, num: int = None) -> None:
        update_snapshot = pytestconfig.getoption("--update-snapshots")
        node_name = re.sub(r'-(\d+)', '', request.node.name)
        test_name = f"{str(Path(node_name))}[{str(sys.platform)}]"
        test_dir = str(Path(request.node.name)).split('[', 1)[0]
        test_file_name = str(os.path.basename(Path(request.node.fspath))).strip('.py')
        filepath = (
                Path(request.node.fspath).parent.resolve()
                / 'snapshots'
                / test_file_name
                / test_dir
        )
        filepath.mkdir(parents=True, exist_ok=True)
        if num is None:
            file = filepath / f'{test_name}_{current_tab_name}.png'
        else:
            file = filepath / f'{test_name}_{current_tab_name}_{num}.png'
        # Create a dir where all snapshot test failures will go
        results_dir_name = (Path(request.node.fspath).parent.resolve()
                            / "snapshot_tests_failures")
        test_results_dir = (results_dir_name
                            / test_file_name / test_name)
        # Remove a single test's past run dir with actual, diff and expected images
        if test_results_dir.exists():
            new_dir_name = f"{test_results_dir}_{uuid.uuid4()}"
            test_results_dir.rename(new_dir_name)
        if update_snapshot:
            file.write_bytes(img)
            print("--> Snapshots updated. Please review images")
        if not file.exists():
            file.write_bytes(img)
            print("--> New snapshot(s) created. Please review images")

        if file.exists() and not update_snapshot:
            # Load the first image to get its dimensions
            img_a = Image.open(BytesIO(img))
            width_a, height_a = img_a.size

            # Load the second image
            img_b = Image.open(file)
            width_b, height_b = img_b.size

            # If the dimensions of the second image do not match the first image, resize it
            if width_a != width_b or height_a != height_b:
                img_b = img_b.resize((width_a, height_a), Image.LANCZOS)

            # Continue with the rest of the comparison logic using the resized second image
            img_diff = Image.new("RGBA", img_a.size)
            mismatch = pixelmatch(img_a, img_b, img_diff, threshold=threshold, fail_fast=fail_fast)
            if mismatch == 0:
                return
            else:
                # Create new test_results folder
                test_results_dir.mkdir(parents=True, exist_ok=True)
                img_diff.save(f'{test_results_dir}/Diff_{test_name}_{current_tab_name}.png')
                img_a.save(f'{test_results_dir}/Actual_{test_name}_{current_tab_name}.png')
                img_b.save(f'{test_results_dir}/Expected_{test_name}_{current_tab_name}.png')
                pytest.fail("--> Snapshots DO NOT match!")

    return compare


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("playwright-snapshot", "Playwright Snapshot")
    group.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Update snapshots.",
    )
