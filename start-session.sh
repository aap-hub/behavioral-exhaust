#!/bin/bash
# UGA Harness Development Session
# Run this to create/attach the tmux session

SESSION="uga-harness"
ACPX="$HOME/Library/pnpm/global/5/.pnpm/openclaw@2026.3.13_@discordjs+opus@0.10.0_@napi-rs+canvas@0.1.96_@types+express@5.0.6/node_modules/openclaw/extensions/acpx/node_modules/.bin/acpx"

# Create session if it doesn't exist
tmux has-session -t $SESSION 2>/dev/null
if [ $? != 0 ]; then
    echo "Creating new tmux session: $SESSION"
    
    # Main window: Claude Code office hours
    tmux new-session -d -s $SESSION -n claude -c ~/Projects/uga-harness
    
    # Second window: file browser / editor
    tmux new-window -t $SESSION -n files -c ~/Projects/uga-harness
    
    # Third window: git / general terminal
    tmux new-window -t $SESSION -n git -c ~/Projects/uga-harness
    
    # Set up the claude window with the ACPX command ready to paste
    tmux send-keys -t $SESSION:claude "cd ~/Projects/uga-harness" Enter
    tmux send-keys -t $SESSION:claude "export ACPX=\"$ACPX\"" Enter
    tmux send-keys -t $SESSION:claude "export CLAUDE_MODEL=claude-opus-4-6" Enter
    tmux send-keys -t $SESSION:claude "echo 'Ready. Create session with:'" Enter
    tmux send-keys -t $SESSION:claude "echo '\$ACPX claude sessions new --name uga-harness-design'" Enter
    tmux send-keys -t $SESSION:claude "echo '\$ACPX claude set-mode bypassPermissions -s uga-harness-design'" Enter
    tmux send-keys -t $SESSION:claude "echo 'Then run office hours with:'" Enter
    tmux send-keys -t $SESSION:claude "echo '\$ACPX --timeout 3600 --approve-reads claude -s uga-harness-design \"Run /office-hours\"'" Enter
    
    # Go back to first window
    tmux select-window -t $SESSION:claude
fi

# Attach
tmux attach -t $SESSION
