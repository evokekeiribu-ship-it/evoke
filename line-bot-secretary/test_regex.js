const text = "```json\n{ \"a\": 1 }\n```";
try {
    let newJsonStr = text.replace(/\`\`\`json/g, '').replace(/\`\`\`/g, '').trim();
    console.log(newJsonStr);
} catch (e) {
    console.error(e);
}
