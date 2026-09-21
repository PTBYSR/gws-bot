require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const { clearMongoAuth, closeMongoConnection } = require('./useMongoDBAuthState');

(async () => {
    console.log('Clearing MongoDB Auth state...');
    await clearMongoAuth();
    await closeMongoConnection();
    console.log('Done.');
})();
