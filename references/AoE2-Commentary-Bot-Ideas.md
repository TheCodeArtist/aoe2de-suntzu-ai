# AoE2 Commentary Bot Ideas

## Overview
A bot that accepts periodic screenshots of an ongoing AoE2 game and returns relevant comments/statements for live stream display.

---

## 1. Build Order Timing Analysis
- Compare villager count vs game time against standard benchmarks (e.g., 20 pop scouts should hit Feudal at 9:15, 23 pop archers at 10:30)
- Detect clicking up times and compare to expected timings (e.g., "Player clicked Castle Age at 17:30 - that's ahead of the standard 20 min timing!")
- Track age-up progress and announce when players are advancing

## 2. Economy Distribution Commentary
- Analyze villager distribution across resources (food/wood/gold/stone) and comment on balance
- Flag economy imbalances (e.g., "Floating 600 wood in early Feudal - should be spending on farms!")
- Compare to recommended distributions (e.g., for crossbow transition: 14 food, 12 wood, 9 gold)

## 3. Opening/Strategy Recognition
- Identify build orders being executed (Drush FC, Scout opening, MAA into Archers, etc.)
- Detect civilization-specific strategies (Lithuanian instant drush, Persian douche, Hoang push with Celts)
- Comment on opening choices relative to civilization matchup and map type

## 4. Military Composition Analysis
- Identify unit counters using the extensive counter-unit guide (e.g., "Making knights into mass pikes - that's a bad trade!")
- Flag hidden bonus damage interactions (e.g., "Those halberdiers do +60 damage to Battle Elephants!")
- Suggest army adjustments based on what opponent is producing

## 5. Map Control & Positioning
- Comment on hill control ("Fighting uphill - that's +25% damage against them!")
- Track forward building placement (siege workshops, monasteries on hills)
- Note walling status and vulnerability windows

## 6. Upgrade Tracking
- Flag missing critical upgrades (Fletching, Bloodlines, armor upgrades)
- Announce key tech completions (Crossbow upgrade, Ballistics, unique techs)
- Compare upgrade timing to recommended sequences

## 7. Civilization-Specific Commentary
- Highlight civ bonuses being utilized (e.g., "Mongols hunting bonus giving faster Feudal time")
- Note missed civ synergies (e.g., "Lithuanians not collecting relics for knight attack bonus")
- Reference tier rankings for matchup analysis (S-tier vs D-tier civ commentary)

## 8. Resource Management
- Track market usage and comment on buy/sell efficiency
- Note Saracen market abuse potential (5% trading fee)
- Flag stone mining for castle timing predictions

## 9. Game Phase Transitions
- Announce phase shifts (early aggression vs boom approach)
- Predict upcoming plays based on building placement and economy setup
- Comment on TC count and boom progress

## 10. Water/Hybrid Map Specifics
- Track fishing ship counts and dock production
- Comment on water control and fire galley vs galley choices
- Note land-water balance decisions

## 11. Population & Production Efficiency
- Track idle TC time and flag when villager production stops ("TC idle for 30 seconds - losing economy!")
- Monitor population milestones against game clock
- Detect housed situations (population capped without house production)
- Count military production buildings and comment on production capacity

## 12. Scouting & Information Warfare
- Note scout survival ("Scout still alive at 15 min - great for map awareness!")
- Flag unscouted areas and blind spots
- Comment on information advantages ("Player has seen enemy gold mining - knows it's not a drush")
- Track relics found/collected especially for Lithuanians, Aztecs, Burgundians

## 13. Micro & Tactical Decisions
- Detect patrol vs attack-move usage (document notes attack-move is bugged)
- Comment on formation choices (flank formation vs line for dodging mangonels)
- Note attack-ground usage with siege units
- Flag quickwall attempts and success/failure

## 14. Laming & Early Aggression
- Detect boar/sheep stealing attempts
- Comment on deer pushing efficiency
- Track forward villager movements for tower rushes or forwards
- Note mill placement relative to berries (pre-mill drush detection)

## 15. Matchup-Specific Insights
- Reference best openings chart for each civ matchup
- Comment on favorable/unfavorable matchups ("Goths vs Mayans - Huskarls will dominate late game")
- Note counter-civ strategies being employed or missed

## 16. Landmark Timings
- Announce first military unit production timing
- Track Castle drop timing and placement (offensive vs defensive)
- Note University timing for Ballistics
- Flag Monastery timing for relic collection

## 17. Resource Exhaustion Predictions
- Track sheep/boar consumption rates
- Predict berry exhaustion and farm transition timing
- Note gold/stone pile depletion and expansion needs
- Comment on fish boom efficiency on water maps

## 18. Defensive Assessment
- Evaluate wall completion percentage and vulnerability
- Note tower placement for resource denial
- Track castle/krepost positioning for map control
- Comment on defensive depth (layers of walls, building placement)

## 19. Trade & Late Game Economy
- Track trade cart/cog production for team games
- Note relic gold generation especially for Aztecs (+33% bonus)
- Comment on Feitoria construction for Portuguese
- Flag gold-efficient unit transitions (trash wars preparation)

## 20. Player Tendencies & Patterns
- Detect aggressive vs defensive playstyle from early decisions
- Note boom vs pressure approach choices
- Comment on adaptation speed to opponent's strategy
- Track commitment levels to specific strategies (all-in vs flexible)

## 21. Empire Wars Specifics
- Different baseline expectations for starting economy
- Track immediate opening choice (Eagles/Scouts/Archers)
- Note faster engagement timings expected in this mode

## 22. Error Detection
- Flag common mistakes (no loom before aggression exposure, wrong upgrade order)
- Note inefficient villager pathing at lumber camps
- Detect over-investment in one unit type
- Comment on floating resources that should be spent

## 23. Comparative Analysis
- Side-by-side economy comparison between players
- Military value comparison (resource investment in armies)
- Tech advantage tracking (who has key upgrades first)
- Score trajectory prediction based on current trends

## 24. Historical/Meta References
- Compare to pro player strategies ("This is the Hoang push style!")
- Note meta-relevance of choices ("Pre-mill drush is the 2023 meta")
- Reference tournament strategies when applicable

## 25. Audio/Visual Cue Suggestions
- Trigger alerts for key moments (age-ups, big fights, raids)
- Suggest replay-worthy moments for highlights
- Flag potential game-deciding engagements

---

## Reference Data from Document

### Standard Feudal Age Timings
| Population | Arrival Time | Common Opening |
|------------|--------------|----------------|
| 19 pop | 8:50 | Fast scouts |
| 20 pop | 9:15 | Scouts |
| 21 pop | 9:40 | Scouts, MAA, Archers |
| 22 pop | 10:05 | MAA, Archers |
| 23 pop | 10:30 | MAA, Archers |

### Key Time Constants
- Villager creation: 25 seconds
- Loom: 25 seconds
- Wheelbarrow: 75 seconds
- Feudal Age research: 130 seconds (2:10)
- Castle Age research: 160 seconds (2:40)

### Economy Balance for Castle Age Transition
| Army Composition | Villagers | Food | Wood | Gold | Stone |
|------------------|-----------|------|------|------|-------|
| Archers → Crossbows | 35 | 14 | 12 | 9 | 0 |
| Knights/Camels | 35 | 18 | 9 | 8 | 0 |

### Civilization Tiers (Arabia)
- **S-Tier:** Chinese, Incas, Georgians, Mongols, Mayans
- **A-Tier:** Portuguese, Khmer, Malians, Byzantines, Malay, Persians, Aztecs
- **B-Tier:** Saracens, Slavs, Armenians, Gurjaras, Franks, Vietnamese, Tatars, Romans, Lithuanians, Hindustanis, Berbers, Ethiopians, Koreans, Italians, Goths, Bohemians
- **C-Tier:** Spanish, Magyars, Dravidians, Turks, Japanese, Britons, Burmese, Cumans, Vikings, Burgundians, Teutons, Bengalis, Huns, Poles
- **D-Tier:** Sicilians, Celts, Bulgarians

---

## Implementation Notes
- Bot should accept screenshots at configurable intervals
- OCR or image recognition needed to extract game state data
- Comments should be contextual and not repetitive
- Priority system for most relevant/interesting observations
- Consider humor and entertainment value for stream audience
```

---

