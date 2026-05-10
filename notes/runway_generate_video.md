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

