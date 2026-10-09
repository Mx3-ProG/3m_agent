export type MicrophoneState =
  | "off"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking";

export type MicrophoneEvent =
  | "ENABLE"
  | "SPEECH_FINAL"
  | "REQUEST_STARTED"
  | "RESPONSE_AUDIO_STARTED"
  | "RESPONSE_AUDIO_ENDED"
  | "DISABLE";

export function transitionMicrophone(
  state: MicrophoneState,
  event: MicrophoneEvent,
  continuous: boolean,
): MicrophoneState {
  if (event === "DISABLE") return "off";
  if (event === "ENABLE") return "listening";
  if (event === "SPEECH_FINAL" && state === "listening") return "transcribing";
  if (event === "REQUEST_STARTED") return "thinking";
  if (event === "RESPONSE_AUDIO_STARTED") return "speaking";
  if (event === "RESPONSE_AUDIO_ENDED") return continuous ? "listening" : "off";
  return state;
}
