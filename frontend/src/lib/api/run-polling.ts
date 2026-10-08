/** One request at a time; terminal responses and disposal stop future polling. */
export function pollRuns<T>(
  load: (signal: AbortSignal) => Promise<T>,
  receive: (value: T) => void,
  shouldContinue: (value: T) => boolean,
  failure: (error: unknown) => void,
) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  async function tick() {
    try {
      const value = await load(controller.signal);
      if (controller.signal.aborted) return;
      receive(value);
      if (shouldContinue(value)) timer = setTimeout(tick, 2000);
    } catch (error) {
      if (!controller.signal.aborted) failure(error);
    }
  }
  void tick();
  return () => { controller.abort(); clearTimeout(timer); };
}
