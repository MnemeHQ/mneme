"""Translation tests: Antigravity PreToolUse payloads -> canonical ToolEvents."""

import json

import pytest

from mneme.integrations.antigravity.adapter import BadHookEvent, parse_hook_event


def _payload(tool_name, args, workspaces=("c:/ws/proj",)):
    return {
        "toolCall": {"name": tool_name, "args": args},
        "stepIdx": 3,
        "conversationId": "conv-1",
        "workspacePaths": list(workspaces),
        "modelName": "gemini-test",
    }


class TestWriteToFile:
    def test_maps_to_write_with_complete_content(self):
        event = parse_hook_event(
            json.dumps(
                _payload(
                    "write_to_file",
                    {
                        "TargetFile": "c:/ws/proj/src/mod.py",
                        "CodeContent": "x = 1\n",
                        "Overwrite": False,
                    },
                )
            )
        )
        assert event.tool_name == "Write"
        assert event.file_path == "c:/ws/proj/src/mod.py"
        assert event.tool_input["content"] == "x = 1\n"
        assert event.cwd == "c:/ws/proj"

    def test_missing_workspace_paths_gives_empty_cwd(self):
        event = parse_hook_event(
            json.dumps(_payload("write_to_file", {"TargetFile": "a.py"}, workspaces=[]))
        )
        assert event.cwd == ""


class TestReplaceFileContent:
    def test_maps_to_edit(self):
        event = parse_hook_event(
            json.dumps(
                _payload(
                    "replace_file_content",
                    {
                        "TargetFile": "c:/ws/proj/src/mod.py",
                        "TargetContent": "old line",
                        "ReplacementContent": "new line",
                    },
                )
            )
        )
        assert event.tool_name == "Edit"
        assert event.tool_input["old_string"] == "old line"
        assert event.tool_input["new_string"] == "new line"


class TestMultiReplaceFileContent:
    def test_maps_chunks_to_sequential_edits(self):
        event = parse_hook_event(
            json.dumps(
                _payload(
                    "multi_replace_file_content",
                    {
                        "TargetFile": "c:/ws/proj/src/mod.py",
                        "ReplacementChunks": [
                            {"TargetContent": "a", "ReplacementContent": "b"},
                            {"TargetContent": "c", "ReplacementContent": "d"},
                        ],
                    },
                )
            )
        )
        assert event.tool_name == "MultiEdit"
        assert event.tool_input["edits"] == [
            {"old_string": "a", "new_string": "b"},
            {"old_string": "c", "new_string": "d"},
        ]

    def test_non_list_chunks_raise(self):
        with pytest.raises(BadHookEvent):
            parse_hook_event(
                json.dumps(
                    _payload(
                        "multi_replace_file_content",
                        {"TargetFile": "f", "ReplacementChunks": "nope"},
                    )
                )
            )


class TestReadOnlyAndMalformed:
    @pytest.mark.parametrize(
        "tool_name,args",
        [
            ("view_file", {"AbsolutePath": "c:/x"}),
            ("list_dir", {"DirectoryPath": "c:/x"}),
            ("grep_search", {"SearchPath": "c:/x", "Query": "q"}),
            ("run_command", {"CommandLine": "echo hi", "Cwd": "c:/x"}),
        ],
    )
    def test_read_only_and_unmapped_tools_return_none(self, tool_name, args):
        assert parse_hook_event(json.dumps(_payload(tool_name, args))) is None

    def test_malformed_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_hook_event("this is not json")

    def test_missing_tool_call_raises(self):
        with pytest.raises(BadHookEvent):
            parse_hook_event(json.dumps({"stepIdx": 0}))

    def test_non_object_payload_raises(self):
        with pytest.raises(BadHookEvent):
            parse_hook_event(json.dumps([1, 2, 3]))

    def test_mutating_tool_with_bad_args_raises(self):
        """A Write whose TargetFile is not a string must not be guessed at."""
        with pytest.raises(BadHookEvent):
            parse_hook_event(
                json.dumps(_payload("write_to_file", {"TargetFile": 42}))
            )
