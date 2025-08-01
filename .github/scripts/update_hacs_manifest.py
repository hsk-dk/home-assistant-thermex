"""Update the manifest file."""

import json
import os
import sys


def update_manifest():
    """Update the manifest file."""
    version = "0.0.0"
    manifest_path = False
    dorequirements = False

    for index, value in enumerate(sys.argv):
        if value in ["--version", "-V"]:
            version = str(sys.argv[index + 1]).replace("v", "")
        if value in ["--path", "-P"]:
            manifest_path = str(sys.argv[index + 1])[1:-1]
        if value in ["--requirements", "-R"]:
            dorequirements = True

    if not manifest_path:
        sys.exit("Missing path to manifest file")

    with open(
        f"{os.getcwd()}/{manifest_path}/manifest.json",
        encoding="UTF-8",
    ) as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    if dorequirements:
        requirements = []
        with open(
            f"{os.getcwd()}/requirements.txt",
            encoding="UTF-8",
        ) as file:
            for line in file:
                requirements.append(line.rstrip())

        new_requirements = manifest["requirements"].copy()
        for requirement in requirements:
            req = requirement.split("==")[0].lower()
            # Remove any existing requirement with the same name (case-insensitive, ignoring version)
            new_requirements = [
                x for x in new_requirements if not x.lower().startswith(req)
            ]
            # Add the new requirement
            new_requirements.append(requirement)
        manifest["requirements"] = new_requirements

    with open(
        f"{os.getcwd()}/{manifest_path}/manifest.json",
        "w",
        encoding="UTF-8",
    ) as manifestfile:
        manifestfile.write(
            json.dumps(
                {
                    "domain": manifest["domain"],
                    "name": manifest["name"],
                    **{
                        k: v
                        for k, v in sorted(manifest.items())
                        if k not in ("domain", "name")
                    },
                },
                indent=4,
            )
        )


update_manifest()
