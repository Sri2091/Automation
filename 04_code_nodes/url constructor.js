// Process all items from input
const allItems = $input.all();

return allItems.map(item => {
  // Handle different response formats for each item
  const response = item.json;
  let fileKey;
  
  // Try different possible key names from Supabase response
  if (response.Key) {
    fileKey = response.Key;
  } else if (response.key) {
    fileKey = response.key;
  } else if (response.name) {
    fileKey = response.name;
  } else if (response.path) {
    fileKey = response.path;
  }
  
  // Remove bucket name from key if it's included
  if (fileKey && fileKey.startsWith('comfyui/')) {
    fileKey = fileKey.replace('comfyui/', '');
  }
  
  const publicUrl = `https://cofswhisytptdxmhljvp.supabase.co/storage/v1/object/public/comfyui/${fileKey}`;
  
  return {
    json: {
      url: publicUrl
    }
  };
});