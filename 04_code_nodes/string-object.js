const string1 = $input.first().json['Prompt 1'];
const string2 = $input.first().json['Prompt 2'];
const string3 = $input.first().json['Prompt 3'];
const string4 = $input.first().json.row_number;

return [
  { json: { prompt1: string1 } },
  { json: { prompt2: string2 } },
  { json: { prompt3: string3 } }
  // { json: { prompt: string4 } }
];
