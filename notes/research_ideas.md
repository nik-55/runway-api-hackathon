# Hackathon Ideas

## 1. Chronicle — AI Personal Memory Documentary Maker

### Pitch
Anyone can preserve a family story, personal history, or oral tradition as a professional documentary — just by talking and sharing photos.

### What Makes It Uncopyable
Runway's app is a media creation tool (you know what you want → generate it). Chronicle is a conversation-driven creative intelligence (AI figures out what SHOULD be generated → generates it → stitches a narrative arc). The Character interviewer makes editorial decisions, not just responsive generation.

### How It Works
1. User uploads family photos + starts a conversation with a Runway Character (via LiveKit)
2. Character conducts a guided documentary interview — asks intelligent follow-up questions, decides what to explore deeper
3. As the conversation progresses, the agent autonomously:
   - Animates uploaded photos into gentle video clips (image-to-video)
   - Generates contextual B-roll for memories without photos (text-to-video)
   - Creates narration bridges (TTS)
   - Adds ambient sound matching the era/emotion (sound effects)
   - Structures everything into a 3-act emotional arc
4. Output: a complete 3-5 minute personal documentary
5. Optional: auto-dub into 29 languages for diaspora families (voice dubbing)

### Editorial Intelligence Layer (what's hard and impressive)
- Character decides when to animate a photo vs. generate new B-roll vs. use a narration bridge
- Evaluates generated clips for emotional tone before including them
- Structures the narrative arc (not just sequential generation)
- Asks questions to fill gaps in the story
- The character itself becomes the narrator — writes narration in the voice of the story

### APIs Used
- Runway Characters / GWM-1 (LiveKit, real-time interview)
- Image to Video (animate uploaded photos)
- Text to Video (generate contextual B-roll)
- Text to Speech / ElevenLabs TTS (narration)
- Sound Effects (ambient audio)
- Voice Dubbing (multilingual output — optional)

### Target Market
- Families wanting to preserve grandparent/elder stories
- Ancestry platforms (Ancestry.com, MyHeritage)
- Funeral services (legacy video packages)
- Cultural preservation / oral history NGOs
- History museums and libraries

### Demo Strategy
Show: empty screen → 3-minute conversation with the character about a family memory → documentary plays. Judges watch a mini-film about something real and emotional. The output IS the demo.

### Why It Wins
- Creativity: solves a universal human need (preserving memories) in a novel way
- Technical depth: 5+ APIs chained with editorial logic between each step
- Impact: every family on earth wants this; clear B2B path
- Polish: the documentary output is inherently high-quality and emotional
