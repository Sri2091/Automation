// n8n Code Node - Dynamic Seed Generator (Always New Seeds)
// Configuration
const config = {
  randMax: $input.all()[0]?.json?.randMax || 1125899906842624, // ComfyUI default max
  randMin: $input.all()[0]?.json?.randMin || 0,                // ComfyUI default min    
  step: $input.all()[0]?.json?.step || 1,                     // Step increment
  count: $input.all()[0]?.json?.count || 1                    // How many seeds to generate
};

// Calculate random range (exact ComfyUI logic)
const randomRange = (config.randMax - Math.max(0, config.randMin)) / (config.step / 10);

// Generate fresh random seed using ComfyUI formula
function generateNewSeed() {
  const seed = Math.floor(Math.random() * randomRange) * (config.step / 10) + config.randMin;
  return Math.floor(Math.max(config.randMin, Math.min(config.randMax, seed)));
}

// Generate seeds - always new/random every execution
const results = [];
for (let i = 0; i < config.count; i++) {
  const seed = generateNewSeed();
  results.push({
    seed: seed,
    index: i + 1,
    timestamp: new Date().toISOString()
  });
}

// Return only the seed
return [{
  json: {
    seed: results[0].seed
  }
}];