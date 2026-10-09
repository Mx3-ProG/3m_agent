import assert from "node:assert/strict";
import test from "node:test";

import { transitionMicrophone } from "./microphone-machine.ts";

test("continuous mode returns to listening after TTS", () => {
  let state = transitionMicrophone("off", "ENABLE", true);
  state = transitionMicrophone(state, "SPEECH_FINAL", true);
  state = transitionMicrophone(state, "REQUEST_STARTED", true);
  state = transitionMicrophone(state, "RESPONSE_AUDIO_STARTED", true);
  state = transitionMicrophone(state, "RESPONSE_AUDIO_ENDED", true);
  assert.equal(state, "listening");
});

test("manual microphone off always wins", () => {
  assert.equal(transitionMicrophone("speaking", "DISABLE", true), "off");
  assert.equal(transitionMicrophone("listening", "DISABLE", true), "off");
});

test("TTS cannot transition back to transcription", () => {
  const speaking = transitionMicrophone("thinking", "RESPONSE_AUDIO_STARTED", true);
  assert.equal(transitionMicrophone(speaking, "SPEECH_FINAL", true), "speaking");
});
