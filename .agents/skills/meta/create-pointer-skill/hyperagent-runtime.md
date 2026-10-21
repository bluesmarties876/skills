# Hyperagent pointer runtime contract

This is host-specific packaging, not a second copy of a skill's method. A pointer's
stored documentation remains exactly one Execute line naming its repo resolver.

## When a pointer needs a local script

Inspect the complete resolved repo folder and its documented credential use. Do not
infer this from the pointer body, credential presence alone, or a partial listing.

| Skill requirements | Local registration |
| --- | --- |
| Contains implementation scripts, including scripts that need no secrets | One no-op credential_anchor.py |
| Uses RunWithCredentials naming itself, even if the command lives elsewhere | One no-op credential_anchor.py and its documented credential slots |
| Borrows an API skill's credentials | The credential-owning skill must have a registered script; also anchor this pointer if it carries scripts itself |
| Instructions only, with no own credential-wrapper use | No anchor required |
| Folder or credential requirements unknown | Stop and report what could not be inspected; unknown is not instruction-only |

Hyperagent can refuse credential preparation with a no-scripts error before it starts
a repo command. Preserving credentialSchema without a registered script is insufficient.
A placeholder on disk is also insufficient: register it through CreateSkill or
UpdateSkillAndScripts, then confirm the save before treating it as installed.

## Generate and register

Use create-pointer-skill's planner, fetched from its resolved repo folder:

```
python3 create_pointer_skill.py plan --repo OWNER/REPO --name SKILL \
  --repo-skill-md /tmp/repo_skill.md --runtime required \
  --anchor-out /tmp/new-pointer/credential_anchor.py --json
```

Create the scratch directory first. The output file must be new; an existing file is
refused. The planner generates a self-contained no-op anchor, writes no credentials,
and emits a scripts array containing its absolute filePath and a description. Pass
that array to the host's create/update tool. For instruction-only skills, use
--runtime none without --anchor-out, which emits an empty scripts array.

On collapse, remove the declared implementation scripts and register the anchor in
the same proposed update. Never remove and upsert the same filename. Inspect any
existing credential_anchor.py: a matching name does not prove it is a no-op. Unknown
content is not disposable, and the collapse sync check still compares all declared
scripts. Do not exempt anchors by filename from lost-content checks.

Credential slots belong to the skill that owns them. Preserve documented slots and
stored values; never read or copy a value, and never duplicate a borrowed API token.

## Run the real code

1. Read the saved pointer and confirm availableScripts declares the anchor where required.
2. FetchSkillScripts prepares the local registered file and credentials. It returns the
   anchor, not the implementation. Do not use its directory to locate repo scripts.
3. Resolve and fetch the real scripts from the repo, including sibling dependencies.
4. Run pure scripts with python3 from the extracted folder. For credentialed commands,
   call RunWithCredentials naming the credential-owning skill and use the extracted
   repo script path. Do not run the anchor as a substitute for the real operation.

Running the anchor is harmless but is not a test of the repo script or its credentials.
A draft is not a saved registration. Before save, report runtime setup pending; after
save, verify the declared file and preparation path. Only claim an end-to-end runtime
pass if a safe real repo command actually ran.

## Existing pointers and repo writes

A pointer body can be correct while its runtime registration is missing. Creation and
adoption must report that gap on existing pointers, not silently rewrite them. When a
person asks for repair, add the anchor without changing the one-line body, discovery
metadata or credential values. Inspect filename collisions before replacing anything.

Do not publish a local runtime anchor in place of the real repo scripts. A repo update
that introduces scripts must also identify which existing local pointers need registration;
landing that repo commit does not update every workspace's saved skill automatically.
