// n8n Function Node Code - Counter that increments by 1 each execution

// Method 1: Using Workflow Static Data (Recommended)
// This stores the counter value in the workflow's static data

// Get current counter value from static data, default to 0 if not exists
const staticData = this.getWorkflowStaticData('global');
let counter = staticData.counter || 0;

// Increment the counter
counter += 1;

// Save the updated counter back to static data
staticData.counter = counter;

// Return the incremented value
return [
  {
    json: {
      counter: counter,
      message: `Execution #${counter}`,
      timestamp: new Date().toISOString()
    }
  }
];

// Alternative Method 2: Using Global Variables (if available in your n8n setup)
/*
// Get global variable, default to 0 if not exists
let counter = $vars.counter || 0;

// Increment the counter
counter += 1;

// Set the updated counter back to global variable
$vars.counter = counter;

// Return the incremented value
return [
  {
    json: {
      counter: counter,
      message: `Execution #${counter}`,
      timestamp: new Date().toISOString()
    }
  }
];
*/

// Alternative Method 3: Using External Database/File (for persistence across n8n restarts)
/*
// This would require additional nodes like HTTP Request to external API
// or File operations to read/write counter from external storage
// Example structure:
// 1. Read counter from external source
// 2. Increment counter
// 3. Write counter back to external source
// 4. Return incremented value
*/