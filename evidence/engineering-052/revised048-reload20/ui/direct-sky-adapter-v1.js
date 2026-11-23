async function directSkyPress(key){if(globalThis.objWindow.id!==globalThis.objContext.windowId)throw new Error('Current window differs from guarded context');await sky.press_key({window:globalThis.objWindow,key});}
async function directSkyRefresh(){return globalThis.objGame.getAXState();}
