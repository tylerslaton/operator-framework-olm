#!/usr/bin/env python

import os
import git
import argparse
import subprocess
import re

from datetime import date
from github import Github, UnknownObjectException, GithubException

REMOTES_DICT = {
    "api": "https://github.com/operator-framework/api",
    "operator-registry": "https://github.com/operator-framework/operator-registry",
    "operator-lifecycle-manager": "https://github.com/operator-framework/operator-lifecycle-manager",
    "upstream": "https://github.com/openshift/operator-framework-olm",
}

def get_params():
    parser = argparse.ArgumentParser(
        description="OLM's upstream/downstream sync automation"
    )
    parser.add_argument(
        "--clone-repository",
        default=False,
        help="Configures whether the repository will be cloned",
    )
    parser.add_argument(
        "--script-path",
        default="./scripts/sync.sh",
        help="Configures whether the sync bash script is located",
    )
    args = parser.parse_args()

    return args

def clone_repository(fork_repo, username, token):
    try:
        git.Repo.clone_from(f'https://{username}:{token}@github.com/{fork_repo}', "sync-dir")
        os.chdir('sync-dir')
    except:
        print(f"Failed to clone repo {fork_repo.full_name}")
        raise

def add_remotes(repo):
    for k, v in REMOTES_DICT.items():
        if k in repo.remotes:
            continue
        try:
            repo.create_remote(k, v)
        except:
            print(f"Failed to create {k} {v} remote")
            raise

def fetch_remotes(repo):
    for remote in repo.remotes:
        try:
            remote.fetch()
        except:
            print(f"Failed to fetch the {remote} remote")
            raise

def create_candidate_branch(repo, branch_name):
    try:
        repo.git.checkout(b=branch_name)
    except repo.exec.GitCommandError as e:
        # repo.git.checkout("upstream/master", b=branch_name)
        raise e

def run_syncing_scripts(script_path):
    subprocess.run(script_path, check=True)

def create_pull_request(repo, pr_title, fork_branch_head):
    try:
        repo.create_pull(title=pr_title, body=pr_title, base="master", head=fork_branch_head)
    except GithubException as ge:
        # TODO: handle case where pull request already exists.
        print("failed to create a new PR", ge)
        raise

def sync(token, args):
    g = Github(login_or_token=token)
    github_user = g.get_user()

    try:
        fork_repo_name = f'{github_user.login}/operator-framework-olm'
        # fork_repo = g.get_repo(fork_repo_name)
    except UnknownObjectException:
        print("failed to find fork", fork_repo_name)
        raise

    if args.clone_repository == "true":
        print("Cloning the repository")
        clone_repository(fork_repo_name, github_user.login, token)
    
    repo = git.Repo(search_parent_directories=True)

    # TODO: setup gitconfig environment?

    print("Adding repository remotes")
    add_remotes(repo)

    print("Fetching upstream remotes")
    fetch_remotes(repo)

    today = date.today().strftime('%Y-%m-%d')
    branch_name = f"sync-{today}"

    print(f"Creating new candidate {branch_name} branch")
    create_candidate_branch(repo, branch_name)

    print("Running the syncing script")
    run_syncing_scripts(args.script_path)

    print("Checking whether a sync PR should be created")
    length = len(list(repo.iter_commits(rev="upstream/master..HEAD")))
    print("Length of commits", length)

    if length > 0: 
        print(f'Pushing changes to {fork_repo_name}')
        print("Result of push: ", repo.git.push('--set-upstream', 'origin', branch_name))

        print("Creating pull request")
        pr_title = f"Sync {today}"
        upstream_repository = g.get_repo("openshift/operator-framework-olm")
        create_pull_request(upstream_repository, pr_title, f'{github_user.login}:{branch_name}')
        print(f'Pull request created with name {pr_title}')

if __name__ == "__main__":
    args = get_params()

    token = os.environ["GITHUB_TOKEN"]
    sync(token, args)
