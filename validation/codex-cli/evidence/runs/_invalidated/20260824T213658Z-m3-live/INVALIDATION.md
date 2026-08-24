Classification: design-gap discovery - no enforcement conclusion.

The production PreToolUse matcher is ^apply_patch$ (M1d-b scope), so an
all-shell session never fires PreToolUse and the lazy baseline capture
never ran. At Stop the audit correctly late-captured a baseline and
disclosed the audit as inactive (visible in transcript-c1: "hook: Stop"
completed, shell_made.txt landed, no block, no false accusation).

Fix: register SessionStart as the primary baseline moment; PreToolUse
remains a secondary net. Definition change requires one more /hooks trust
round.
