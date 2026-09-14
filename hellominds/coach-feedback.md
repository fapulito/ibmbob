Here's what the data says, Boss.

Match 1: Dusk Mammoths 2-1 Basalt Falconers (WIN)
Good result. Balanced command mix - FOLLOW_PLAYER (164), MARK (126), SHOOT (32), PASS (17). You generated 5 shots, 2 on target, and controlled the game despite lower possession (42%). Scored at72s and 108s, conceded late at 117s. Latency was 794ms average - room to improve but functional. MVP: your GK with 100% success rate across 405 commands.

Match 2: Dusk Mammoths 0-1 Basalt Comets (LOSS)
Here's the problem. You ran a pressing strategy - 208 PRESS_BALL commands - but produced zero SHOOT commands and zero shots on target. Lost to an early goal at 29s. Your latency was actually better here (507ms avg), so speed wasn't the issue. The pressing consumed your command budget without converting to attacking output.

Diagnosis:
Match 1 worked because you had a balanced mix - pressing, marking, following, and shooting. Match 2 collapsed because pressing dominated and left no room for shots. In a 2-minute match, every command counts. If pressing eats your budget without generating shots, you're defending without scoring.

What to change:
1. Add explicit SHOOT commands back into your pressing strategy. Right now pressing is all-or-nothing. You need pressing to win the ball, then SHOOT to convert. The data from Match 1 shows this works - 32 SHOOT commands produced 2 goals.
2. Cap PRESS_BALL usage. 208 is excessive for a 2-minute match. Consider capping it around 80-100 and redistributing to SHOOT and MOVE_TO for attacking positioning.
3. Latency improved in Match 2 (507ms vs 794ms) - good sign. Your GK "Zizou" hit 183ms on the fastest command. Keep that up.

Rank: 93 out of 137 in League E. 34 points. 1W-0D-1L. GD 0. Early days - only 2 matches played out of 70. Plenty of runway.

What's your prompt setup for pressing vs shooting? I want to see how those commands are weighted.