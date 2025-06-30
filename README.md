<a href="https://livekit.io/">
  <img src="./.github/assets/livekit-mark.png" alt="LiveKit logo" width="100" height="100">
</a>

# Python Outbound Voicemail Classifier

<p>
  <a href="https://docs.livekit.io/agents/overview/">LiveKit Agents Docs</a>
  •
  <a href="https://livekit.io/cloud">LiveKit Cloud</a>
  •
  <a href="https://blog.livekit.io/">Blog</a>
</p>

This example demonstrates an AI agent that automatically calls a voicemail service, transcribes the messages, classifies them using an LLM, and saves the results. It uses LiveKit SIP for outbound calls and the Python Agents Framework.

This example is built for a post-call analysis workflow, not for real-time conversation.

## How It Works

The agent's workflow is as follows:

1.  **Dispatch**: The agent is triggered via a dispatch command, receiving the phone number of the voicemail service to call.
2.  **Outbound Call**: It uses a LiveKit SIP Trunk to place an outbound call to the specified number.
3.  **Listen & Transcribe**: Once the call is connected, the agent listens to the audio stream (the recorded voicemail message being played back). It uses Deepgram to transcribe the speech into text in real-time.
4.  **Post-Call Analysis**: After the call ends, the agent sends the complete transcript to an OpenAI LLM (e.g., GPT-4o) for classification. The LLM categorizes the message based on predefined instructions (e.g., `PRISE_RDV`, `ANNULATION_RDV`).
5.  **Save Results**: The agent saves the classification and the full transcript to a local file named `voicemail_log.txt` for permanent record-keeping.

## Dev Setup

Clone the repository and install dependencies to a virtual environment:

```shell
git clone https://github.com/livekit-examples/outbound-caller-python.git
cd outbound-caller-python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python agent.py download-files
```

Set up the environment by copying `.env.example` to `.env.local` and filling in the required values:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `OPENAI_API_KEY`
- `SIP_OUTBOUND_TRUNK_ID`
- `DEEPGRAM_API_KEY`

Run the agent worker:

```shell
python3 agent.py dev
```

Now, your worker is running and waiting for dispatch jobs to make outbound calls.

### Making a call

You can dispatch an agent to call a voicemail service by using the `lk` CLI. The `phone_number` in the metadata should be the number of the voicemail box you want the agent to check.

```shell
lk dispatch create \
  --new-room \
  --agent-name outbound-caller \
  --metadata '{"phone_number": "+1234567890"}'
```

After the call, check the `voicemail_log.txt` file in the project's root directory for the classified transcript.

```
