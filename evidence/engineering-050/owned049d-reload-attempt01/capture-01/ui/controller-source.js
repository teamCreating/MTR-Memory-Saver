/* Actual guarded controller before first reload input */
async function(key, label, kind) {
  if (!/^[a-z0-9-]+$/.test(label)) throw new Error('Invalid unique receipt label');
  var { raw, state } = await readNativeState();
  var age = Date.now() - Date.parse(state.observed_at);
  if (state.pid !== expectedGamePid || age < 0 || age > 5000) throw new Error('Fresh native process identity required');
  if (kind === 'resume' && !(state.in_world === true && state.screen === 'net.minecraft.client.gui.screens.PauseScreen' && state.paused === true)) throw new Error('Pause screen guard rejected');
  if (kind === 'reload' && !(state.in_world === true && state.screen === null && state.paused === false && state.window_active === true && state.mouse_grabbed === true && state.native_pending === 0 && state.native_settled === true && state.registered_count === 1091 && state.registered_declarations === 1092)) throw new Error('Eligible focused game guard rejected');
  if (kind === 'reload') {
    var rows = (await fs.readFile(vmRoot + '/.cache/acceptance/owned-049d-reload-recorder-attempt01/journal.jsonl', 'utf8')).trim().split('\n').map(JSON.parse);
    var selected = [...rows].reverse().find(r => ['published','ineligible','capture_failed','initialization_failed'].includes(r.event.kind));
    if (!selected || selected.event.kind !== 'published' || Date.now()-Date.parse(selected.event.receipt_closed_at) > 5000) throw new Error('No fresh eligible recorder publication');
    var samples = (await fs.readFile(vmRoot + '/.cache/acceptance/owned-049d-reload-observation-attempt01/samples.jsonl', 'utf8')).trim().split('\n').map(JSON.parse);
    if (!samples.some(s => s.observation?.verified === true)) throw new Error('Consumer baseline unavailable');
  }
  await fs.writeFile(uiOutput + '/' + label + '-before.json', raw, { flag: 'wx' });
  var receipt = { method: kind === 'reload' ? 'native_f3_t' : kind, provider: 'computer-use @oai/sky', pid: expectedGamePid, window: gameWindow, key, before_snapshot_sha256: crypto.createHash('sha256').update(raw).digest('hex'), issued_at: new Date().toISOString(), succeeded: false };
  try { await sky.press_key({ window: gameWindow, key }); receipt.succeeded = true; }
  catch (error) { receipt.error = String(error); throw error; }
  finally { receipt.confirmed_at = new Date().toISOString(); await fs.writeFile(uiOutput + '/' + label + '.json', JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' }); nodeRepl.write(receipt); }
}
