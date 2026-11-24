# Contribute a recipe

Start with [the research guide](skills/tweakin/references/new-app.md). Describe the behavior you want, its entry points, and the behavior that must continue working.

Keep app-specific hooks in their own source directory and document the exact app version. Include the source license, upstream attribution, reproducible build instructions, and an acceptance record. Share small source patches and synthetic fixtures. Do not upload an app executable or a personalized download as a fixture.

The Instagram command contains Instagram-specific storage and signing decisions. Add a separate recipe for another app. Extract shared code when two working recipes demonstrate the same requirement.

Run the commands in the root README and add new distributable paths to `public-files.json`. The distribution list applies even while this repository is private. Never attach generated IPAs, certificates, enrollment models, or unredacted acquisition logs to an issue or pull request.
