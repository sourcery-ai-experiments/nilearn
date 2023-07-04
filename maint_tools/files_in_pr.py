"""Script to get all files touched by PRs.

- Request diff of each PR and save it to a file.
- List all files involved in PRs.

Possibility to exclude PRs based on their title.
Possibility to exclude files or not based on their path.
"""
# noqa: D103

import re
import shutil
from pathlib import Path
from warnings import warn

import pandas as pd
import requests
import yaml
from rich import print

USERNAME = "Remi-Gau"

# may require a token if run often
TOKEN_FILE = Path(__file__).parent.joinpath("token.txt")

# repo to check
GH_USERNAME = "nilearn"
GH_REPO = "nilearn"

DEBUG = False

# Set to true to rely on presaved diffs
USE_LOCAL = False

OUTPUT_FOLDER = Path(__file__).parent / "tmp"
OUTPUT_FILE = OUTPUT_FOLDER / "output.csv"

EXCLUDE_PR = {
    "title": [
        "Format",
        "mypy",
        "Formatting",
        "Refactor",
        "refactor",
        "Simplify",
        "IGNORE",
        "logger",
    ]
}
# EXCLUDE_PR = {}

# use pre-commit config "exclude / include files" config
# to know which files are already covered by pre-commit
USE_PRE_COMMIT_CONFIG = True
EXCLUDE_FILES = "^$"
INCLUDE_FILES = "^.*$"


def root_folder():
    """Get the root folder of the repo."""
    return Path(__file__).parent.parent


def include_from_pre_commit_config():
    """Get the include and exclude regex from the pre-commit config."""
    pre_commit_config = root_folder() / ".pre-commit-config.yaml"
    with open(pre_commit_config) as f:
        config = yaml.safe_load(f)
    exclude = config["exclude"]
    return exclude


def print_to_output(
    output_file: Path,
    all_files: list[str],
    exclude_files: str,
):
    """Print all files touched by PRs to file.

    Parameters
    ----------
    output_file : Path
        _description_
    all_files : list[str]
        _description_
    """
    unique_files = set(all_files)
    unique_files = sorted(unique_files)

    is_new = []
    precommit = []
    nb_occurences = []
    conflict_risk = []
    for file in unique_files:
        is_new.append(not (root_folder() / file).exists())
        precommit.append(re.match(exclude_files, file) is None)
        nb_occurences.append(all_files.count(file))
        conflict_risk.append(precommit[-1] is False and is_new[-1] is False)

    data = {
        "files": unique_files,
        "nb_occurences": nb_occurences,
        "conflict_risk": conflict_risk,
        "is_new": is_new,
        "precommit": precommit,
    }
    df = pd.DataFrame(data)
    df.to_csv(output_file, index=False)


def save_diffs(pulls, auth, output_folder: Path):
    """Save the diff of each PR to a file.

    Parameters
    ----------
    pulls : _type_
        _description_
    auth : None | tuple[str, str]
        _description_
    output_folder : Path
        _description_
    """
    for i, pull_ in enumerate(pulls):
        if DEBUG and i == 2:
            break
        print(f"\n{pull_['number']}, {pull_['title']}")
        diff = get_this_pr_diff(url=pull_["diff_url"], auth=auth)
        if diff is None:
            continue
        save_diff_to_file(
            number=pull_["number"],
            name=pull_["title"],
            diff=diff,
            output_folder=output_folder,
        )


def save_diff_to_file(number: int, name: str, diff: str, output_folder: Path):
    """Save the diff of a PR to a file.

    Parameters
    ----------
    number : int
        _description_
    name : str
        _description_
    diff : str
        _description_
    output_folder : Path
        _description_
    """
    filename = (
        output_folder
        / f"{number}_{name.replace(' ', '_').replace('/', '_')}.diff"
    )
    with open(filename, "w") as f:
        f.write(diff)


def get_list_of_prs(gh_username: str, gh_repo: str, auth=None):
    """List open PRs for a given repo.

    Parameters
    ----------
    gh_username : str
        _description_
    gh_repo : str
        _description_
    auth : None | tuple[str, str], optional
        _description_, by default None

    Returns
    -------
    _type_
        _description_
    """
    base_url = "https://api.github.com/repos/"
    url = f"{base_url}{gh_username}/{gh_repo}/pulls?per_page=100"
    response = requests.get(url, auth=auth)
    if response.status_code != 200:
        warn(f"Error {response.status_code}: {response.text}")
        return None
    return response.json()


def get_this_pr_diff(url: str, auth=None):
    """Get the diff of a PR.

    Parameters
    ----------
    url : str
        _description_
    auth : None | tuple[str, str], optional
        _description_, by default None

    Returns
    -------
    _type_
        _description_
    """
    response = requests.get(url, auth=auth)
    if response.status_code != 200:
        warn(f"Error {response.status_code}: {response.text}")
        return
    return response.text


def list_all_files_in_prs(
    input_folder: Path,
    exclude_pr: dict[str, list[str]] = None,
    include_pr: dict[str, list[str]] = None,
):
    """List all the files touched by PRs by reading their diffs from files.

    Parameters
    ----------
    input_folder : Path
        _description_
    exclude_pr : dict[str, list[str]], optional
        _description_, by default None
    include_pr : dict[str, list[str]], optional
        _description_, by default None

    Returns
    -------
    _type_
        _description_
    """
    list_exclude_pr = []

    all_files = []
    pulls = input_folder.glob("*.diff")
    for pull_ in pulls:
        pr_number = pull_.stem.split("_")[0]
        pr_title = pull_.stem.split("_")[1:]

        include = True
        if include_pr and all(
            ex not in pr_title for ex in include_pr["title"]
        ):
            include = False
        if not include:
            continue

        if exclude_pr and any(ex in pr_title for ex in exclude_pr["title"]):
            print(f"[red]excluding {pr_number}, {' '.join(pr_title)}[/red]")
            list_exclude_pr.append(f"#{pr_number}")
            continue

        print(f"{pr_number}, {' '.join(pr_title)}")
        diff = Path(pull_).read_text()
        for line in diff.splitlines():
            if line.startswith("diff --git "):
                this_file = line.split(" ")[2][2:]
                all_files.append(this_file)

    print()
    print(", ".join(list_exclude_pr))
    print()

    return all_files


def main():
    """Get PRs, save their diffs to files and list all files touched by PRs."""
    if not USE_LOCAL:
        shutil.rmtree(OUTPUT_FOLDER, ignore_errors=True)

    OUTPUT_FILE.unlink(missing_ok=True)
    OUTPUT_FOLDER.mkdir(exist_ok=True)

    TOKEN = None
    if TOKEN_FILE.exists():
        with open(Path(__file__).parent.joinpath("token.txt")) as f:
            TOKEN = f.read().strip()

    if USE_PRE_COMMIT_CONFIG:
        EXCLUDE_FILES = include_from_pre_commit_config()

    auth = None if USERNAME is None or TOKEN is None else (USERNAME, TOKEN)
    if not USE_LOCAL:
        pulls = get_list_of_prs(
            gh_username=GH_USERNAME, gh_repo=GH_REPO, auth=auth
        )
        save_diffs(pulls=pulls, auth=auth, output_folder=OUTPUT_FOLDER)

    all_files = list_all_files_in_prs(
        input_folder=OUTPUT_FOLDER, exclude_pr=EXCLUDE_PR
    )

    print_to_output(
        output_file=OUTPUT_FILE,
        all_files=all_files,
        exclude_files=EXCLUDE_FILES,
    )


if __name__ == "__main__":
    main()
