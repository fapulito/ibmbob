Copied from: https://console.scorestudio.ai/upcoming/manako-element-tcg-grading-starter-pack

Operational brief, scoring logic, deployment flow, and miner requirements.
Editorial View
This private-track challenge focuses on grading the condition of a trading card from one combined PNG containing the front and back views side by side.

The dataset is predominantly composed of professionally graded Pokémon cards. A small percentage of challenges may feature cards from other trading card games, so miners should build models that generalize beyond Pokémon. All reference grades and subgrades follow the ACE Grading standard.

Release date: TBD.

Element Specification
Element ID: manako/TCGGrading
Challenge Track: Private
Challenge Version: 1.0
Input: One PNG containing the front and back of the same card side by side
Ground Truth: Professional ACE grades and subgrades
Grading Categories
The four fields under Grading_Features and the final Header.card_grade are scored.

Field	Weight	What to evaluate
subgrade_surface	25%	Scratches, print lines, stains, dents, whitening, and other surface imperfections
subgrade_corners	25%	Corner sharpness and overall corner wear
subgrade_edges	25%	Whitening, chipping, dents, and other edge damage
subgrade_centering	10%	Front and back centering of the artwork within the card borders
card_grade	15%	Overall ACE card grade, reflecting the combined condition of the card
Each grade is evaluated independently against its ACE reference value. The closer a prediction is to the reference, the more of that field's contribution the miner earns. Surface, edges, and corners account for 75% of the final score; centering contributes 10%, and the holistic final card grade contributes 15%.

Miner Architecture
As with the other private-track challenges, miners submit a Docker image containing a prediction server. The validator sends one combined front/back card image to the miner, the miner downloads and processes it, and the server returns the four predicted subgrades plus the final card grade.

How it works:

Build a Docker image with the model and prediction logic.
Push the image to a container registry.
Register the image on-chain.
Receive one combined front/back PNG URL from the validator.
Download the image and run inference on both card views.
Return the four ACE-aligned subgrades and the final ACE card grade.
Have all five values scored independently against verified ground truth.
Server Specification
The Docker image must run a FastAPI server on port 8000 with this endpoint:

POST /challenge
Each request identifies one challenge and provides a single PNG containing the front and back views side by side, matching the starter examples:

{
  "challenge_id": "abc-123",
  "image_url": "https://example.com/card-front-back.png"
}
Response Schema
The miner only needs to predict Header.card_grade and the Grading_Features object. All other ground-truth metadata under Header and Card is contextual and is not part of the score.

{
  "challenge_id": "abc-123",
  "prediction": {
    "Header": {
      "card_grade": 7
    },
    "Grading_Features": {
      "subgrade_surface": 6,
      "subgrade_centering": 10,
      "subgrade_edges": 10,
      "subgrade_corners": 10
    }
  },
  "processing_time": 2.5
}
Field Types
Field	Type	Notes
challenge_id	string	Echo the validator-provided challenge ID
prediction.Header.card_grade	number	Overall ACE card grade
prediction.Grading_Features.subgrade_surface	number	ACE-aligned surface subgrade
prediction.Grading_Features.subgrade_centering	number	ACE-aligned centering subgrade
prediction.Grading_Features.subgrade_edges	number	ACE-aligned edge subgrade
prediction.Grading_Features.subgrade_corners	number	ACE-aligned corner subgrade
processing_time	number	End-to-end inference time in seconds
Field names and capitalization must match the schema above. Return all five scored values for every challenge; an omitted or invalid field cannot earn its assigned contribution.

Ground-Truth Shape
The validator's full ground-truth record may contain card identity, provenance, and grader metadata in addition to the scored features:

{
  "Header": {
    "year": "2020",
    "set_name": "Promo",
    "card_name": "Mewtwo",
    "rarity_raw": "—",
    "finish": "—",
    "card_number": "184/SM-P",
    "language": "other",
    "card_grade": 7
  },
  "Grading_Features": {
    "subgrade_surface": 6,
    "subgrade_centering": 10,
    "subgrade_edges": 10,
    "subgrade_corners": 10
  },
  "Card": {
    "edition": "none"
  }
}
Only Header.card_grade and Grading_Features are prediction targets used by the scoring metric. Miners do not need to predict any other fields under Header or Card.

Evaluation Metric
The final challenge score is the weighted combination of five independent field scores:

score = 0.25 * surface_score
      + 0.25 * edges_score
      + 0.25 * corners_score
      + 0.10 * centering_score
      + 0.15 * card_grade_score
Each field score rewards predictions according to their distance from the ACE reference value. The final per-field distance curve and numeric tolerance will be published with the validator contract.

Deployment Flow
1. Set up the environment
git clone https://github.com/score-technologies/turbovision.git
cd turbovision
pip install -e .
2. Implement the model
Implement card analysis using both views contained in the combined PNG, then return the four required fields under prediction.Grading_Features and the final grade under prediction.Header.card_grade.

3. Build the Docker image
sv deploy-pt-miner --tag v1.0.0 --no-push --no-commit --no-start
4. Test locally
docker run -p 8000:8000 your-username/pt-solution:v1.0.0
5. Deploy
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=***
sv deploy-pt-miner --tag v1.0.0
This flow builds the Docker image, pushes it to the configured registry, and registers it on-chain.

6. Grant Score access
Manually grant Score read access to the private GHCR package:

Open https://github.com/users/YOUR_USERNAME/packages/container/pt-solution/settings.
Under Manage access, choose Invite teams or people.
Add DataAndMike with Read access.
Spot-Check Verification
The validator may pull the submitted Docker image and run a test challenge against it. The live endpoint and submitted image must serve the same model and return the same response format.

The GHCR private package must be shared with Score (DataAndMike). Without this access, the miner cannot pass image spot checks.

Example Challenges
Each PNG below contains the front and back view of one card. The linked JSON is that exact card's ACE ground-truth record.

Card	Card grade	Surface	Centering	Edges	Corners	Assets
Erika's Clefable — Gym Heroes 3/132	5	4	10	7	7	PNG · Ground truth JSON
Pikachu — Promo 218/SV-P	10	10	10	10	10	PNG · Ground truth JSON
Ampharos — Neo Genesis 1/111	1	1	10	9	10	PNG · Ground truth JSON
Pikachu — Lost Origin TG05/TG30	9	9	10	10	9	PNG · Ground truth JSON
Mewtwo — Promo 184/SM-P	7	6	10	10	10	PNG · Ground truth JSON
Charizard — Base 4/102	3	2	10	5	5	PNG · Ground truth JSON
The four subgrades and card_grade are prediction targets. All remaining ground-truth metadata is shown for context and is not included in the challenge score.