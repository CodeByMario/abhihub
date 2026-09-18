import { WebWorkerMLCEngineHandler } from "https://esm.run/@mlc-ai/web-llm";

// Instantiate the WebWorkerMLCEngineHandler to communicate with the main thread
const handler = new WebWorkerMLCEngineHandler();

self.onmessage = (msg) => {
    handler.onmessage(msg);
};
