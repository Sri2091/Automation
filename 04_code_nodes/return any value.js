const items = $input.all();
// Get the ID from the specific Edit Fields15 node
const sharedId = $('Google Drive1').first().json.id;

return items.map((item, index) => {
  return {
    json: {
      ...item.json,
      // Use existing ID if item has one, otherwise use the shared ID from Edit Fields15
      id: item.json.id || sharedId
    },
    binary: item.binary || {}
  };
});