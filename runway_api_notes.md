https://docs.dev.runwayml.com/

Runway API supports following features via its api:

- **Image to Video**
- **Text to Video**
- **Video to Video**
  - Runway's state-of-the-art model to edit, transform and generate video.
- **Text to Image**
- **Character Performance**
  - Act two: Runway's next-generation motion capture model.
- **Text to Speech**
- **Voice Isolation**
  - Remove background noise from audio.
- **Sound Effect**
  - Turn text into sound effects for your videos, voice-overs or video games.
- **Voice Dubbing**
  - Translate audio to up to 29 other languages.
- **Speech to Speech**
  - Change voice while preserving emotion and tone.
- **Runway Characters**

## Models:

### Generate images

- **runway/Gen-4 Image**
  - Runway's best in class image generation model.
  - Text/Image to Image

- **runway/Gen-4 Image Turbo**
  - Runway's fastest and most cost efficient image generation model.
  - Text/Image to Image

- **google/Gemini 3 Pro**
  - Google's most capable image generation model with 4K resolution support.
  - Text/Image to Image

- **google/Gemini 2.5 Flash**
  - State-of-the-art image generation and editing model.
  - Text/Image to Image

- **openai/GPT Image 2**
  - OpenAI's latest image generation model with up to 4K resolution.
  - Text/Image to Image

### Generate videos

- **runway/Gen-4.5**
  - Runway's state-of-the-art text to video and image to video model.
  - Image to Video
  - Text to Video

- **runway/Gen-4 Turbo**
  - Runway's fastest Image to Video generation model.
  - Image to Video

- **runway/Gen-4 Aleph**
  - Runway's state-of-the-art model to edit, transform and generate video.
  - Video to Video

- **runway/Act Two**
  - Runway's next-generation motion capture model.
  - Image/Video to Video

- **google/Veo 3**
  - High quality video generation with audio and speech.
  - Text/Image to Video
  - Sound

- **google/Veo 3.1**
  - High quality video generation with audio and speech.
  - Text/Image to Video
  - Sound

### Generate audio

- **elevenlabs/Text to Speech**
  - Generate lifelike speech with nuanced intonation and emotion.
  - Text to Speech

- **elevenlabs/Voice Isolation**
  - Remove background noise from audio.
  - Audio to Audio

- **elevenlabs/Sound Effect**
  - Turn text into sound effects for your videos, voice-overs or video games.
  - Text to Audio

- **elevenlabs/Voice Dubbing**
  - Translate audio to up to 29 other languages.
  - Audio to Audio

- **elevenlabs/Speech to Speech**
  - Change voice while preserving emotion and tone.
  - Audio to Audio


## Runway Characters

- Build fully custom conversational characters powered by GWM-1, Runway’s General World Model. Generate expressive digital personas from a single image—photorealistic or animated, human or non-human—with full control over voice, personality, knowledge, and actions. No fine-tuning required.

What you can build
Customer support
Deploy branded characters that maintain your visual identity. Use actual representatives or create stylized brand ambassadors.

Learning & development
Bring training programs to life with interactive tutors and coaches capable of extended educational conversations.

Brand experiences
Your mascots and animated characters can now hold real-time conversations. Your creative vision doesn’t stop at static content.

Interactive characters
Game hosts, dungeon masters, companions, and contextual avatars for immersive experiences.

Getting started
Custom Characters
Create your own character from a single image — no training required.
Embedded Widget
Add a Character to any website with a single script tag — no server required.
Custom Voices
Design a new voice from a text prompt or clone one from an audio sample.
LiveKit Agents
Bring your own agent — you control STT, LLM, and TTS, Runway provides the avatar video layer.


Hair Makeover NextJS Example
This application demonstrates how to integrate with the Runway API to generate hair makeovers based on a user-uploaded selfie and a selected hairstyle.

Upload a selfie.
Select a hairstyle.
Click "Generate".


Generate Video Chrome Extension
This Chrome extension connects to the Gen-4 Video API, allowing you to generate a video from any image on a webpage.

Try On Chrome Extension
This Chrome extension connects to the Gen-4 Image API, allowing you to virtually try on clothing by uploading reference images of both yourself and desired outfits.


Figma plugin: Image and Video Generator
Now you can either type in a prompt to Generate an image, or select frames to generate images with references, or generate videos!

Generate avatar video from audio or text
POST
/v1/avatar_videos
Start an asynchronous task to generate a video of an avatar speaking. Provide speech with type: "audio" (audio file) or type: "text" (text script for TTS). Poll GET /v1/tasks/:id to check progress and retrieve the output video URL once complete.

Authentication
Authorization
Use the HTTP Authorization header with the Bearer scheme along with an API key.

Headers
X-Runway-Version
Required
string
The version of the RunwayML API being used. You can read more about versioning here.

This field must be set to the exact value 2024-11-06.

Request body
model
Required
string
The model to use for avatar video generation.

This field must be set to the exact value gwm1_avatars.

avatar
Required
RunwayPresetAvatar (object) or CustomAvatar (object)
The avatar configuration for the session.

One of the following shapes:
RunwayPresetAvatar
object
A preset avatar from Runway.

type
Required
string
This field must be set to the exact value runway-preset.

presetId
Required
string
Accepted values:"game-character", "music-superstar", "game-character-man", "cat-character", "influencer", "tennis-coach", "human-resource", "fashion-designer", "cooking-teacher"
ID of a preset avatar.

CustomAvatar
object
A user-created avatar.

type
Required
string
This field must be set to the exact value custom.

avatarId
Required
string
<uuid>
^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{...
Show pattern
ID of a user-created avatar.

speech
Required
AudioInput (object) or TextInput (object)
The speech source for avatar video generation. Either an audio file or text script.

One of the following shapes:
AudioInput
object
Provide an audio file for the avatar to speak.

type
Required
string
This field must be set to the exact value audio.

audio
Required
string
A HTTPS URL, Runway or data URI containing an encoded audio. See our docs on audio inputs for more information.

One of the following shapes:
string
[ 13 .. 2048 ] characters
^https:\/\/.*
A HTTPS URL.

string
[ 13 .. 5000 ] characters
^runway:\/\/.*
A Runway upload URI. See https://docs.dev.runwayml.com/assets/uploads for more information.

string
[ 13 .. 16777216 ] characters
^data:audio\/.*
A data URI containing encoded media.

TextInput
object
Provide text for the avatar to speak via TTS.

type
Required
string
This field must be set to the exact value text.

text
Required
string
[ 1 .. 3000 ] characters
Text script for speech-driven video generation.

voice
RunwayPresetVoice (object) or CustomVoice (object)
Optional voice override for TTS. If not provided, the avatar's configured voice is used.

One of the following shapes:
RunwayPresetVoice
object
A preset voice from the Runway API.

type
Required
string
This field must be set to the exact value preset.

presetId
Required
string
Accepted values:"victoria", "vincent", "clara", "drew", "skye", "max", "morgan", "felix", "mia", "marcus", "summer", "ruby", "aurora", "jasper", "leo", "adrian", "nina", "emma", "blake", "david", "maya", "nathan", "sam", "georgia", "petra", "adam", "zach", "violet", "roman", "luna"
CustomVoice
object
A custom voice created via the Voices API.

type
Required
string
This field must be set to the exact value custom.

id
Required
string
<uuid>
^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{...
Show pattern
Responses
200 Success
Response Schema: application/json
id
Required
string
<uuid>
^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{...
Show pattern
The ID of the avatar video task. Use GET /v1/tasks/:id to poll for status and output.

