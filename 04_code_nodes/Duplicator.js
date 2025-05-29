  function duplicateItems(items, times = 3) {
    const duplicated = [];
    items.forEach(item => {
      for (let i = 0; i < times; i++) {
        duplicated.push({
          json: { ...item.json, iteration: i + 1 },
          binary: item.binary
        });
      }
    });
    return duplicated;
  }

  // For n8n Code node:
  return duplicateItems(items, 3);