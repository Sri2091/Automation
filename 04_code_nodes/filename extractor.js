// Process all items, not just the first one
const items = $input.all();

return items.map(item => {
  const binaryData = item.binary;
  const firstBinaryKey = Object.keys(binaryData)[0];
  const filename = binaryData[firstBinaryKey].fileName || firstBinaryKey;
  const cleanName = filename.replace(/\.[^/.]+$/, "");

  return {
    json: { 
      filename: cleanName,
      row_number: item.json.row_number
    },
    binary: binaryData
  };
});