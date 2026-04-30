// pcm-worklet.js — AudioWorklet: capture Float32 @ browser rate, resample to 16kHz PCM16, post to main thread
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    // Browser AudioContext sample rate (e.g. 48000 on mac) comes in from the options
    this.inputRate = options.processorOptions.inputRate || sampleRate;
    this.targetRate = 16000;
    this.ratio = this.inputRate / this.targetRate;
    this.carry = 0; // fractional position for simple linear downsample
    this.buffer = []; // int16 samples accumulating toward one chunk
    this.chunkSize = 1600; // 100ms @ 16kHz
    this.levelSum = 0; // running sum of squared samples for RMS
    this.levelCount = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0]; // mono (or first channel of stereo)
    if (!ch) return true;

    // RMS level for visualization (from raw input, before downsample)
    for (let i = 0; i < ch.length; i++) {
      const v = ch[i];
      this.levelSum += v * v;
      this.levelCount++;
    }

    // Simple linear-interpolation downsample input -> 16kHz
    let pos = this.carry;
    while (pos < ch.length) {
      const idx = Math.floor(pos);
      const frac = pos - idx;
      const s1 = ch[idx] || 0;
      const s2 = ch[idx + 1] !== undefined ? ch[idx + 1] : s1;
      const sample = s1 + (s2 - s1) * frac;
      // Float32 [-1,1] -> int16
      const i16 = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
      this.buffer.push(i16);
      pos += this.ratio;

      if (this.buffer.length >= this.chunkSize) {
        const out = new Int16Array(this.buffer.splice(0, this.chunkSize));
        // Emit audio chunk + current level, sent in one message
        const level = this.levelCount > 0 ? Math.sqrt(this.levelSum / this.levelCount) : 0;
        this.levelSum = 0;
        this.levelCount = 0;
        this.port.postMessage({ pcm: out, level }, [out.buffer]);
      }
    }
    this.carry = pos - ch.length;
    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
