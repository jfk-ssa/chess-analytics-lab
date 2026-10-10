import { analyzeGames, importPgnFiles, LIMITS, sha256 } from './game-import-core.mjs';

let imported = null;
self.onmessage = async (event) => {
  const message = event.data;
  try {
    if (message.type === 'import') {
      imported = null;
      if (message.files.length > LIMITS.files)
        throw new Error(`Choose at most ${LIMITS.files} files.`);
      if (message.files.reduce((sum, file) => sum + file.size, 0) > LIMITS.bytes)
        throw new Error('Files exceed the 10 MiB session limit.');
      const files = [];
      for (const file of message.files) {
        const bytes = await file.arrayBuffer();
        let text;
        try {
          text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
        } catch {
          throw new Error(`${file.name}: invalid UTF-8. Save a plain UTF-8 PGN and retry.`);
        }
        files.push({ name: file.name, text, sha256: await sha256(bytes) });
      }
      imported = await importPgnFiles(files, (progress) =>
        self.postMessage({ type: 'progress', ...progress }),
      );
    } else if (message.type === 'example') {
      imported = await importPgnFiles([message.file], (progress) =>
        self.postMessage({ type: 'progress', ...progress }),
      );
    } else if (message.type === 'analyze') {
      if (!imported) throw new Error('Import games first.');
      if (
        message.options.since &&
        message.options.until &&
        message.options.since > message.options.until
      )
        throw new Error('The start date must be on or before the end date.');
      const result = analyzeGames(
        imported.records,
        message.aliases,
        message.reference,
        message.options,
      );
      self.postMessage({ type: 'analysis', result });
      return;
    } else throw new Error('Unknown import action.');
    self.postMessage({
      type: 'loaded',
      stats: imported.stats,
      players: imported.players,
      rejected: imported.rejected,
      failures: imported.failures,
      sources: imported.sources,
      timeControls: [...new Set(imported.records.map((r) => r.time_control || 'unknown'))].sort(),
    });
  } catch (error) {
    self.postMessage({ type: 'error', message: error.message || 'Game import failed.' });
  }
};
