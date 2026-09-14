#!/bin/bash

# Smart registration script for subnet 44
# Waits until immunity periods expire, then attempts registration

WALLET_NAME="cricket_miner"
HOTKEY_NAME="miner3"
HOTKEY_SS58="5FexQrNyQJP8DXRo5rxMVaTzi4rGcNdZUE6cx9cfYwpGEzV9"
NETUID=44
IMMUNITY_PERIOD=7500
BLOCKS_PER_SECOND=0.0833  # 12 seconds per block
TARGET_WINDOW_START=9062500  # When first immunity windows open
ATTACK_WINDOW_BLOCKS=600  # Try for 600 blocks (~2 hours)
CHECK_INTERVAL=60  # Check every 60 seconds during attack window

echo "================================"
echo "Smart Registration for Subnet 44"
echo "================================"
echo "Wallet: $WALLET_NAME"
echo "Hotkey: $HOTKEY_NAME"
echo "Target window: blocks $TARGET_WINDOW_START - $((TARGET_WINDOW_START + ATTACK_WINDOW_BLOCKS))"
echo ""

# Function to get current block number
get_current_block() {
    btcli subnet metagraph $NETUID 2>/dev/null | grep "block" | head -1 | awk '{print $2}'
}

# Function to calculate time until target block
blocks_to_seconds() {
    local blocks=$1
    echo $(echo "$blocks / $BLOCKS_PER_SECOND" | bc)
}

# Check if already registered
echo "Checking if already registered..."
if btcli subnet metagraph $NETUID 2>/dev/null | grep -q "$HOTKEY_SS58"; then
    echo "✓ Already registered! Finding your UID..."
    btcli subnet metagraph $NETUID 2>/dev/null | grep -B2 -A2 "$HOTKEY_SS58"
    exit 0
fi

echo "Not registered yet. Calculating optimal attack window..."
echo ""

# Get current block
CURRENT_BLOCK=$(get_current_block)
echo "Current block: $CURRENT_BLOCK"

if [ -z "$CURRENT_BLOCK" ]; then
    echo "Error: Could not fetch current block number"
    exit 1
fi

# Calculate blocks until attack window
BLOCKS_TO_WAIT=$((TARGET_WINDOW_START - CURRENT_BLOCK))

if [ $BLOCKS_TO_WAIT -le 0 ]; then
    echo "Attack window already started! Beginning registration attempts..."
    BLOCKS_TO_WAIT=0
else
    SECONDS_TO_WAIT=$(blocks_to_seconds $BLOCKS_TO_WAIT)
    HOURS=$(echo "$SECONDS_TO_WAIT / 3600" | bc)
    MINUTES=$(echo "($SECONDS_TO_WAIT % 3600) / 60" | bc)
    
    echo "Blocks until attack window: $BLOCKS_TO_WAIT"
    echo "Estimated wait time: ${HOURS}h ${MINUTES}m"
    echo ""
    echo "Waiting until block $TARGET_WINDOW_START..."
    echo "This script will check every 5 minutes and start attacking when the window opens."
    echo ""
    
    # Wait loop - check every 5 minutes
    while [ $BLOCKS_TO_WAIT -gt 0 ]; do
        sleep 300  # 5 minutes
        CURRENT_BLOCK=$(get_current_block)
        BLOCKS_TO_WAIT=$((TARGET_WINDOW_START - CURRENT_BLOCK))
        
        if [ $BLOCKS_TO_WAIT -le 0 ]; then
            echo "Attack window reached!"
            break
        fi
        
        SECONDS_TO_WAIT=$(blocks_to_seconds $BLOCKS_TO_WAIT)
        HOURS=$(echo "$SECONDS_TO_WAIT / 3600" | bc)
        MINUTES=$(echo "($SECONDS_TO_WAIT % 3600) / 60" | bc)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Still waiting... ${HOURS}h ${MINUTES}m remaining (block $CURRENT_BLOCK)"
    done
fi

echo ""
echo "================================"
echo "ATTACK WINDOW ACTIVE"
echo "================================"
echo "Attempting registration every $CHECK_INTERVAL seconds"
echo "Will continue for $ATTACK_WINDOW_BLOCKS blocks (~2 hours)"
echo ""

attempt=0
start_block=$(get_current_block)

while true; do
    attempt=$((attempt + 1))
    current_block=$(get_current_block)
    blocks_elapsed=$((current_block - start_block))
    
    # Stop if we've exceeded the attack window
    if [ $blocks_elapsed -gt $ATTACK_WINDOW_BLOCKS ]; then
        echo ""
        echo "Attack window closed after $blocks_elapsed blocks"
        echo "Total attempts: $attempt"
        echo "No slot obtained. Immunity periods may have been too competitive."
        echo ""
        echo "Check your balance: btcli wallet balance --wallet $WALLET_NAME"
        exit 1
    fi
    
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] Block $current_block | Attempt #$attempt (${blocks_elapsed}/${ATTACK_WINDOW_BLOCKS} blocks elapsed)"
    
    # Check if already registered (might have succeeded)
    if btcli subnet metagraph $NETUID 2>/dev/null | grep -q "$HOTKEY_SS58"; then
        echo ""
        echo "✓✓✓ SUCCESS! You are now registered on subnet $NETUID ✓✓✓"
        echo ""
        btcli subnet metagraph $NETUID 2>/dev/null | grep -B2 -A2 "$HOTKEY_SS58"
        echo ""
        echo "Next steps:"
        echo "1. Update fly.io deployment to use hotkey: $HOTKEY_NAME"
        echo "2. Set up Score CLI to commit your element_id on-chain"
        echo "3. Monitor your emissions and validator requests"
        exit 0
    fi
    
    # Attempt registration
    result=$(btcli subnet register --netuid $NETUID --wallet $WALLET_NAME --wallet-hotkey $HOTKEY_NAME 2>&1 <<INNER_EOF
y

INNER_EOF
)
    
    if echo "$result" | grep -q "✓"; then
        echo "  → Registration transaction succeeded! Checking metagraph..."
        sleep 5
    elif echo "$result" | grep -q "HotKeyAlreadyRegisteredInSubNet"; then
        echo "  → Already registered (verifying in metagraph...)"
    else
        echo "  → Registration failed (subnet still full or outcompeted)"
    fi
    
    echo ""
    sleep $CHECK_INTERVAL
done
