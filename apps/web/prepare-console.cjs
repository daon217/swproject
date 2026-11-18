const fs=require('node:fs');
const path=require('node:path');
const root=__dirname, dest=path.join(root,'public','console');
fs.mkdirSync(dest,{recursive:true});
for(const file of ['index.html','app.js','shared','pages'])
  fs.cpSync(path.join(root,file),path.join(dest,file),{recursive:true});
