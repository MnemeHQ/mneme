"""#571: relative tool paths resolve against the SDK payload ``cwd``.

Runs the shared matrix with ``cwd`` = the project and the host process cwd
elsewhere, through the real ``mneme check`` CLI.
"""
from mneme.integrations.agent_sdk import MnemeAgentSdk
from tests.integrations.relative_path_matrix import RelativePathMatrix


class TestAgentSdkRelativePaths(RelativePathMatrix):
    def evaluate(self, layout, runner, tool, tool_input):
        sdk = MnemeAgentSdk(project_dir=layout.project, mode="strict", check_runner=runner)
        return sdk.evaluate_mutation(tool, tool_input, cwd=str(layout.project))
