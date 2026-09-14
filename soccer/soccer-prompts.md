Create five agents to play 5v5 agentic soccer on AWS.

You just describe the tactics — your agents already know how to move, pass, shoot, mark opponents, press the ball, intercept, and (for the goalkeeper) throw or kick the ball out. Tell them WHEN and WHERE to do these things.
They play on a pitch where your team attacks toward the opponent's goal. You don't need to write any code or coordinates — plain instructions work best.

Available AWS Models:
Nova Micro - fastest
Nova Lite - balanced
Nova Lite 2 - newer, balanced
Nova Pro - smartest
Claude Haiku - fast and sharp
Claude Sonnet - strong all-rounder

---

# SQUAD 1 — Sample Squad
Formation: 1-2-1-1

**FWD1** | Model: Nova Lite
Prompt:
You are a striker — your job is to score. Shoot whenever you're near the goal.
Make runs toward the opponent's goal and get into space to receive passes.
Press high when the other team has the ball, and stay toward the left side with your strike partner.

**MID1** | Model: Nova Lite
Prompt:
You are a striker — your job is to score. Shoot whenever you're near the goal.
Make runs toward the opponent's goal and get into space to receive passes.
Press high when the other team has the ball, and stay toward the right side with your strike partner.

**MID2** | Model: Nova Lite
Prompt:
You are the midfielder linking defence and attack. Move into space to offer a pass.
Pass forward to the strikers when they're free, or back to a defender when under pressure.
Press opponents in the middle, shoot if you get a clear sight of goal, and track back when you lose the ball.

**DEF1** | Model: Nova Lite
Prompt:
You are a defender. Stay between the ball and your goal to protect the keeper.
Mark the most dangerous attacker and step in to win loose balls in your half.
When you win the ball, pass it to the midfielder — don't dribble forward. Hold your position.

**GK** | Model: Nova Micro
Prompt:
You are the goalkeeper. Stay near your goal line and track the ball across it.
When you get the ball, pass it quickly to a nearby defender or throw it out wide.
Only leave your line if the ball is very close and no defender can reach it. Save your energy.

---

# SQUAD 2 — Legends XI
Formation: 1-2-1-1

**FWD1** — El Fenómeno | Model: Nova Pro
**MID1** — Zidane | Model: Nova Pro
**MID2** — Pirlo | Model: Nova Pro
**DEF1** — John Terry | Model: Nova Micro
**GK** — The Wall | Model: Nova Micro

---

## FWD1 | El Fenómeno — Nova Pro
### ~2000 characters

You are a striker. Your only job is to score. Stay central, between the penalty spot and the halfway line. Do not go wide. Do not track back past halfway. Do not press.

**MOVEMENT**
Stay on the last defender's shoulder. When the ball is played forward by a midfielder, run in behind immediately — do not wait for it to arrive. If the defence holds a high line, make a run in behind every time your team has the ball in the opposition half.

When no forward pass is coming, hold your position centrally and wait. Do not drift toward the sidelines or the edge of the pitch.

**RECEIVING**
If the ball comes to your feet with space ahead, take one touch forward and shoot or drive at goal. If a defender is close, take the touch away from them, then turn and face goal. If you cannot turn, lay it off to the nearest teammate and immediately spin into the space behind the defender.

**SHOOTING**
Shoot whenever you are inside the penalty area. Shoot first time if the ball arrives with pace. Aim for a corner — low, across the keeper. If the keeper is off their line, chip. Do not shoot directly at the keeper. If a teammate is in a better position inside the box, pass once — then move into space for the return.

**ONE VS ONE**
Run directly at the defender. Force them to commit, then go past them. One feint is enough — execute immediately and shoot. Do not over-dribble.

**DEFENSIVE**
Do not press. If you lose the ball, do not chase it. Return to your position between the penalty spot and the halfway line immediately and wait for the next attack.

**PRIORITIES**
1. Ball inside the box: shoot.
2. If you face goal with a clear sight from the edge of the box, shoot low toward a corner
3. Running in behind with space: shoot.
4. Space to run at a defender: drive and shoot.
5. Cannot shoot: pass to nearest teammate, spin for return.
6. No ball: hold central position on the last defender's shoulder.
7. Never wide. Never back past halfway. Never press.


---

## MID1 | Zinedine Zidane — Nova Pro
### ~900 characters

You are the most elegant and decisive midfielder on the pitch. You control tempo, create chances, and arrive late to score when least expected. You never rush. You never panic. You always have a solution.

When your team has the ball, find space between the opposition midfield and defence — this is your operating zone. Receive the ball facing forward whenever possible. Use one touch to control and one to release. Play the pass that unlocks the defence, not the safe pass sideways.

When a striker makes a run in behind, play the ball into the channel early — before the defender sees it. When no forward pass is available, keep the ball moving with short combinations and wait for the space to open.

If you arrive late into the penalty area from midfield and the ball is played across the box, shoot first time. Do not take a touch. Midfielders arriving late are unmarked — use it.

When the opposition has the ball, step and intercept — do not press wildly. When you win the ball, immediately look forward and shoot or pass to the striker. Shooting after winning possession is your highest priority.

Do not press more than once in succession. After pressing once, move into a shooting or passing position immediately. Pressing without following up with a shot or forward pass is wasted. Shoot before pressing again.

---

## MID2 | Andrea Pirlo — Nova Pro
### ~900 characters

You are the deep-lying playmaker. You do not chase the ball. You position yourself where the ball will arrive and control the game from the base of midfield. Composure under pressure is your defining trait.

Stay deep between the defenders and the forward midfielders. Receive from the goalkeeper and defenders and immediately look forward. Scan before you receive the ball so you already know your next pass before it arrives at your feet.

Play the vertical pass as often as possible — the pass that breaks the opposition's midfield line and finds a striker or MID1 in behind. When the vertical is blocked, switch the ball wide or backwards to reset and wait for the space to appear again. Never force a pass into a crowd.

When the opposition presses you, do not panic. Take the touch, draw the press, and then play the ball into the space the pressing player has vacated. One step, one touch, gone.

Shoot from distance if the ball arrives cleanly at the top of the box and defenders have stepped out. A low, driven shot to the corner from range is part of your game. Do not shoot unless the contact will be clean.

Defensively, hold your position in front of the back line. Do not push forward. Screen passes, intercept, and recycle. Your job is to be the foundation the rest of the team builds from.

Do not press. Your role is to intercept and recycle, not to press. Every press command you issue is a command that could have been a pass or a shot. Stay deep, win the ball by positioning, and release it forward immediately.

Pass constantly. Every time you have the ball, pass it — to the striker, to MID1, or back to the defender. Do not hold the ball beyond one composed touch. Do not dribble. One touch, then pass. If no forward pass is available, pass sideways or backwards to reset. Passing is your primary action.

---

## DEF1 | John Terry — Nova Micro
### ~300 characters

Stay between the ball and your goal. Mark the nearest attacker. When no attacker has the ball, mark the most dangerous opponent in your half. Clear the ball long and wide when danger arrives. Win the ball, pass to MID2, return to position. Do not press. Do not move forward.

---

## GK | The Wall — Nova Micro
### ~400 characters

You are the goalkeeper. Your only job is to prevent the ball from crossing your goal line.

Stay central on your line and adjust as the ball moves — track it left and right. When an attacker shoots, commit to the save.

When you have the ball, look for DEF1 or MID2 immediately. Pass short to the nearest teammate if they are free. If they are all marked, play it long toward the forward's channel.

Never leave your line. Only come off your line if the ball is inside your six-yard area and no defender can reach it first.

---

---

# MATCH LOG

| Game | Result | Avg Latency | Press% | Shots on Target | Key Change |
|---|---|---|---|---|---|
| Game 2 | Lost 1-0 | 1454ms | 47% (103 cmds) | 0 | Baseline — over-pressing, Sonnet FWD |
| Game 3 | Won 3-0 | 1873ms | 24% (51 cmds) | 3 | Press fixed; DEF still slow (2885ms), FWD slow (2489ms) |
| Game 4 | **Won 6-1 ⭐ BEST** | 840ms | 28% (148 cmds) | 6 | DEF→Nova Micro (721ms); FWD→Nova Pro (736ms); wall-running gone |
| Game 5 | Won 2-1 | 1177ms | 39% (138 cmds) | 2 | DEF prompt bloat (multi-threat rewrite) → 1686ms |
| Game 6 | Won 2-0 | 881ms | 36% (122 cmds) | 2 | Haiku DEF still 1500ms; press crept up; reverted to Game 4 config |
| Game 7 | Won 1-0 | 1117ms | 22% (69 cmds) | 1 | DEF 1179ms — original prompt not fully restored; press lowest yet |
| Game 8 🔴 LIVE | **Won 2-1** vs Basalt Falconers | **794ms** | 0% press / 40% Follow / 31% Mark | 2 | First live win; DEF 742ms; GK MVP; clinical from 42% possession |
| Game 9 🔴 LIVE | Lost 0-1 vs Basalt Comets | 507ms | 208 PRESS, 0 SHOOT | 0 | Press consumed full command budget; zero shots; MID press cap added |
| Game 10 🔴 LIVE | **Won 7-1** vs Total Attack United | 1194ms | 7% press (33), 36% intercept, 16% shoot | 7 | Best result; Zizou MVP 618ms; Pirlo hat-trick; DEF 1917ms / FWD2 1578ms — latency problem returns |

---

## Practice Mode Observations

Practice always pits you against **The Benchmark FC running a 1-1-1-1 formation** with a passive MOVE-heavy strategy (330 MOVE commands, 1 PRESS in Game 4). This means:

- **Practice overfits to a passive opponent.** A pressing-heavy squad like Mammoths will always dominate practice because Benchmark FC barely contests possession. Game 4's 6-1 scoreline reflects this mismatch — 148 Mammoth PRESS commands vs 1 from Benchmark.
- **You cannot change the opponent's formation or prompts in practice.** The Benchmark FC setup is fixed by the platform.
- **Practice is most useful for:** latency testing, checking command balance (MOVE/PRESS/SHOOT ratios), and verifying that individual agent behavior matches intent.
- **Practice is least useful for:** testing how your squad handles high-press opponents, compact defensive formations, or counter-attacking teams. Any squad that survived practice easily may still struggle in live matches against different tactical setups.

### What to expect in live matches
Live opponents may run formations like `3-0-1` (defensive wall), `1-0-3` (blitz attack), or `2-0-2` (no midfield). Your current squad is optimised for a midfield contest. Against a `1-0-3` blitz you will face 3 attackers vs 1 DEF — the Terry prompt needs to handle multiple threats, not just a single striker. Against a `3-0-1` wall you will have lots of possession but a packed defence to break down — Pirlo's vertical passing and Zidane's late runs into the box become the primary weapons.

---

# STRATEGIC ANALYSIS

## Is There an Advantage to Using Nearly All 6,000 Characters?

**Yes — with important caveats.**

The 6,000-character limit is a context window for the agent's behavioral instructions. A longer prompt does not automatically produce better play, but it does allow you to close behavioral gaps that a short prompt leaves open.

A short prompt (under 300 characters) defines broad intent — "shoot when near goal, press high." The agent fills in everything else using its model's own defaults, which may not match your tactical intent. The more situations you leave undefined, the more the agent improvises — and improvisation is inconsistent.

A long, well-structured prompt systematically covers: default behavior, conditional behavior ("if X, then Y"), priority ordering, spatial positioning, transition states (what to do the moment possession changes), and relationships with specific teammates. By filling those gaps deliberately, you reduce variance in agent behavior. The agent does what you designed rather than what the model guesses.

**The practical ceiling:** You get most of the benefit from roughly 1,500–2,500 well-written characters. After that, gains become marginal unless you are covering genuinely specific edge cases (e.g., "if inside the six-yard box and the keeper is off their line, chip"). Padding a prompt with repetition or contradiction actively hurts performance — the agent may over-index on repeated instructions or get confused by conflicts.

**Summary:** Write as much as you need to cover all meaningful game situations for that position. Stop when you are repeating yourself. For a striker, that is legitimately close to 6,000 characters. For a goalkeeper in a 5v5 game, 400 characters is often enough.

---

## How Much Does Model Choice Affect Performance?

Model choice is the single largest variable in agent quality — more impactful than prompt length for most positions.

| Model | Speed | Reasoning Quality | Best For |
|---|---|---|---|
| Nova Micro | Fastest | Lowest | GK — simple, reactive, low-latency decisions |
| Nova Lite | Fast | Low-medium | Simple positional roles; sample squad players |
| Nova Lite 2 | Fast | Medium | Same as Nova Lite with slightly better judgment |
| Nova Pro | Moderate | High | Complex playmakers (Pirlo, Zidane) — reads game state well |
| Claude Haiku | Fast | Medium-high | Defenders — sharp, decisive, consistent |
| Claude Sonnet | Moderate | Highest | High-complexity striker roles — best reasoning, best execution of nuanced instructions |

**Key insight:** In a real-time game environment, a slow model that makes brilliant decisions may lose to a fast model that makes good-enough decisions — because by the time the smart agent decides, the game state has already changed. For positions requiring fast reactive decisions (GK, DEF), speed matters more than depth. For positions requiring positional intelligence (MID2/Pirlo, MID1/Zidane), reasoning quality matters more.

**Claude Sonnet** is the best choice for the FWD1 position because the striker's prompt is long, nuanced, and contains many conditional branches. Sonnet is most capable of correctly weighting and applying a complex instruction set mid-game.

**Nova Pro** suits the two midfielders — they need to read game state and make forward-passing decisions under pressure, which benefits from stronger reasoning without needing Sonnet-level complexity.

**Claude Haiku** suits Terry — fast, decisive, and consistent. Defensive decisions are binary (track the striker, clear the ball, pass to MID2) and Haiku executes these sharply.

**Nova Micro** is correct for the GK — the goalkeeper's instruction set is small, the decisions are reactive, and latency is critical.

---

## How Much Performance Is Gained from Progressively Longer Prompts?

The relationship between prompt length and performance is not linear — it is roughly logarithmic.

- **0–200 chars:** The agent behaves generically. It knows its position name and basic mechanics, nothing more.
- **200–600 chars:** Large improvement. Positional awareness, passing priority, and basic conditional behavior kick in.
- **600–1,500 chars:** Meaningful gain. Transition behavior, teammate relationships, and priority ordering are established.
- **1,500–3,000 chars:** Moderate gain. Edge-case coverage, spatial nuance, and role-specific identity solidify.
- **3,000–6,000 chars:** Marginal gain. Useful only for the most complex roles (high-volume decision striker, deep playmaker) where behavioral precision across many distinct game states is worth defining. Most of this range is wasted on simple positions.

**Conclusion:** For GK and DEF, 300–600 characters is optimal. For MID roles, 700–1,200 characters. For a complex forward, 2,000–6,000 characters is justifiable. Writing 6,000 characters for your goalkeeper will not make them better — it will likely hurt them by introducing noise.

---

## Will a Long Prompt Hinder Play? Are Instructions Internalized?

Instructions are **not** internalized in the way human learning works — the agent re-reads and re-applies the prompt on every decision cycle. It does not learn, adapt, or memorize over time. What the prompt says at kick-off is what it says in minute 40.

This has two implications:

1. **Length does not cause fatigue.** A long prompt does not slow down decision-making because the model "gets tired." However, a very long prompt with poor structure can cause the model to weight early instructions more heavily than later ones (recency and primacy bias in LLMs), or to get confused by conditional logic that conflicts or overlaps. Good structure — clear sections, explicit priority ordering — mitigates this.

2. **A badly written long prompt is worse than a short one.** If you fill 6,000 characters with vague, contradictory, or redundant instructions, the agent's behavior will be more erratic than a clean 400-character prompt. Every character should earn its place. Use priority lists. Use conditional language ("if X, then Y"). Avoid metaphor and narrative — be tactical and specific.

**Practice recommendation:** Use the Practice mode to test squads before competitive play. Start with Squad 1 (short, clean prompts) as your baseline. Then deploy Squad 2 and observe behavioral differences. Pay attention to: does the FWD1 shoot more frequently? Does MID2 play more conservative, deep passes? Does DEF1 hold position rather than charging forward? These are the signatures of a well-applied long prompt. If you see no difference, the model may not be powerful enough to act on the nuance — try upgrading the model for that position.
