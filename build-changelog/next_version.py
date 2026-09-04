import subprocess
import sys

import semver


def parse_version(candidate):
    """Return a VersionInfo for `candidate`, or None if it is not a version."""
    if not candidate:
        return None

    try:
        return semver.VersionInfo.parse(candidate.lstrip("v"))
    except (TypeError, ValueError):
        return None


def latest_tagged_version():
    """The highest semver tag in the checkout, or None if there is none.

    Our caller passes release-changelog-builder's `fromTag`, which is NOT
    always a tag. When a repository has exactly one tag the action takes its
    "initial release" path and resolves the root commit instead:

      Only one tag found for the given repository.
      [command] git rev-list --max-parents=0 HEAD
      Resolved previous tag (fafc746e...) from the tags git API

    A commit SHA cannot be bumped, so the last real tag is what we want.

    Requires tags in the workspace, which means the calling workflow must
    check out with `fetch-depth: 0` -- the default depth of 1 fetches
    `--no-tags` and there is nothing here to find. Returns None rather than
    guessing in that case.

    Non-semver tags are skipped instead of being allowed to break the
    selection: `--sort=-v:refname` orders them plausibly but makes no promise
    that the first one parses.

    `--merged HEAD` is load-bearing. Without it a tag on an unmerged branch
    can win -- a v9.9.9 sitting on a side branch turns a 0.10.0 release into
    9.9.10 -- because `git tag --list` spans the whole repository while
    "the version we are releasing from" only means tags in this history.
    """
    try:
        result = subprocess.run(
            ["git", "tag", "--list", "--merged", "HEAD", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    for tag in result.stdout.split():
        version = parse_version(tag)

        if version is not None:
            return version

    return None


requested = len(sys.argv) > 1 and sys.argv[1] or ""
next_release = len(sys.argv) > 2 and sys.argv[2] or "patch"

current_version = parse_version(requested)

# Only ever reached where the previous implementation raised: a parseable
# argument still takes the same path and produces the same output.
if current_version is None:
    current_version = latest_tagged_version()

    if current_version is not None:
        print(
            f"'{requested}' is not a version; "
            f"bumping from tag v{current_version} instead",
            file=sys.stderr,
        )

# Deliberately no invented default here. Emitting something like 0.0.1 would
# open a release pull request in a repository that has never released, which is
# a worse failure than this one -- and our callers write this value straight
# into VERSION. Exit instead, so the log says why rather than showing a
# traceback. The exit code is swallowed by the `$( )` at the call site, so this
# surfaces as an empty output either way; the message is the point.
if current_version is None:
    print(
        f"cannot determine a version to bump: '{requested}' is not a version "
        "and no semver tag was found. If this repository has tags, check out "
        "with fetch-depth: 0 so they are available.",
        file=sys.stderr,
    )
    sys.exit(1)

print(getattr(current_version, f"bump_{next_release}")())
