/// <reference lib="webworker" />

import { renderDriverLuminanceFrame } from '../lib/driverLuminance';
import type { DriverLuminanceSetup } from '../lib/driverLuminance';

type InitMessage = {
  type: 'init';
  generation: number;
  setup: DriverLuminanceSetup;
};

type RenderMessage = {
  type: 'render';
  generation: number;
  requestId: number;
  cameraX: number;
  cameraZ: number;
};

let setup: DriverLuminanceSetup | null = null;
let generation = 0;
const worker = self as unknown as DedicatedWorkerGlobalScope;

worker.onmessage = (event: MessageEvent<InitMessage | RenderMessage>) => {
  const message = event.data;
  if (message.type === 'init') {
    setup = message.setup;
    generation = message.generation;
    return;
  }
  if (!setup || message.generation !== generation) return;
  const frame = renderDriverLuminanceFrame(setup, message.cameraX, message.cameraZ);
  worker.postMessage(
    {
      type: 'frame',
      generation,
      requestId: message.requestId,
      xStart: frame.xStart,
      pixels: frame.pixels.buffer,
    },
    [frame.pixels.buffer],
  );
};

export {};
