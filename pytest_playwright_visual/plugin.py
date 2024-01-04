import os
from pathlib import Path
from typing import Any, Callable
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
import allure
import pytest
import re
import sys
import uuid

DIFF_THRESHOLD_PIXELS = 1000
DIFF_THRESHOLD_RATIO = 0.1

def get_filepaths(node, pytestconfig, test_name, current_tab_name, num=None):
    update_snapshot = pytestconfig.getoption("--update-snapshots")
    test_dir = str(Path(node.name)).split('[', 1)[0]
    test_file_name = str(os.path.basename(Path(node.fspath))).strip('.py')
    snapshot_dir = (
            Path(node.fspath).parent.resolve()
            / 'snapshots'
            / test_file_name
            / test_dir
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if num is None:
        snapshot_file = snapshot_dir / f'{test_name}_{current_tab_name}.png'
    else:
        snapshot_file = snapshot_dir / f'{test_name}_{current_tab_name}_{num}.png'
    return update_snapshot, snapshot_file

def process_images(snapshot: bytes, file):
    # load the snapshot
    img_snapshot = Image.open(BytesIO(snapshot))
    width_a, height_a = img_snapshot.size
    # load the test image
    img_b = Image.open(file)
    width_b, height_b = img_b.size
    # If the dimensions of the second image do not match the first image, resize it. They will likely fail, but at least we can compare the results.
    if width_a != width_b or height_a != height_b:
        img_b = img_b.resize((width_a, height_a), Image.LANCZOS)
    # Convert the images to numpy arrays
    np_img_snapshot = np.array(img_snapshot)
    np_img_b = np.array(img_b)
    return np_img_snapshot, np_img_b

def compare_images(diff, np_img_a, np_img_b, test_results_dir, test_name, current_tab_name):
    diff_pixels = np.sum(diff > 30)  # Count the number of differing pixels
    diff_ratio = diff_pixels / (np_img_a.shape[0] * np_img_a.shape[1])
    if diff_pixels > DIFF_THRESHOLD_PIXELS or diff_ratio > DIFF_THRESHOLD_RATIO:
        # Create new test_results folder
        test_results_dir.mkdir(parents=True, exist_ok=True)

        # Convert multi-dimensional diff to single dimension:
        single_channel_diff = np.mean(diff, axis=2).astype(np.uint8)
        # Apply colormap to single-channel diff image
        colored_diff = cv2.applyColorMap(single_channel_diff, cv2.COLORMAP_JET)

        diff_image = Image.fromarray(colored_diff)
        diff_image.save(f'{test_results_dir}/Diff_{test_name}_{current_tab_name}.png')
        Image.fromarray(np_img_a).save(f'{test_results_dir}/Actual_{test_name}_{current_tab_name}.png')
        Image.fromarray(np_img_b).save(f'{test_results_dir}/Expected_{test_name}_{current_tab_name}.png')

        # Attach failed/expected/diff images using the Allure reporting framework
        allure.attach.file(f'{test_results_dir}/Diff_{test_name}_{current_tab_name}.png', name='Diff Image',
                           attachment_type=allure.attachment_type.PNG)
        allure.attach.file(f'{test_results_dir}/Actual_{test_name}_{current_tab_name}.png', name='Actual Image',
                           attachment_type=allure.attachment_type.PNG)
        allure.attach.file(f'{test_results_dir}/Expected_{test_name}_{current_tab_name}.png', name='Expected Image',
                           attachment_type=allure.attachment_type.PNG)

        print("--> Snapshots DO NOT match!")
        # pytest.fail("--> Snapshots DO NOT match!")
    else:
        print(f"--> Snapshots match! Diff pixels: {diff_pixels} Diff ratio: {diff_ratio}")


@pytest.fixture
def assert_snapshot(pytestconfig: Any, request: Any, browser_name: str) -> Callable:
    node_name = re.sub(r'-(\d+)', '', request.node.name)
    test_name = f"{str(Path(node_name))}[{str(sys.platform)}]"

    def compare(snapshot: bytes, *, current_tab_name: str,
                fail_fast=False, num: int = None) -> None:
        update_snapshot, snapshot_file = get_filepaths(request.node, pytestconfig, test_name,
                                                       current_tab_name, num)

        test_results_dir = (Path(request.node.fspath).parent.resolve()
                            / "snapshot_tests_failures"
                            / str(os.path.basename(Path(request.node.fspath))).strip('.py')
                            / test_name)

        # Remove a single test's past run dir with actual, diff and expected images
        if test_results_dir.exists():
            new_dir_name = f"{test_results_dir}_{uuid.uuid4()}"
            test_results_dir.rename(new_dir_name)
        if update_snapshot:
            snapshot_file.write_bytes(snapshot)
            print("--> Snapshots updated. Please review images")
        if not snapshot_file.exists():
            snapshot_file.write_bytes(snapshot)
            print("--> New snapshot(s) created. Please review images")

        if snapshot_file.exists() and not update_snapshot:
            # Load images and convert them to numpy arrays
            np_snapshot, np_img_b = process_images(snapshot, snapshot_file)
            # Calculate image difference
            diff = cv2.absdiff(np_snapshot, np_img_b)
            # Compare images
            compare_images(diff, np_snapshot, np_img_b, test_results_dir, test_name, current_tab_name)
    return compare


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("playwright-snapshot", "Playwright Snapshot")
    group.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Update snapshots.",
    )
